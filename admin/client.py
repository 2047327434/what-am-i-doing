"""
What Am I Doing - Admin Client
状态采集 + WebSocket 上报 + 系统托盘常驻（无控制台窗口）
用 pythonw.exe 启动，完全无窗口，托盘交互
"""
import asyncio
import ctypes
import ctypes.wintypes
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path

import websockets

# ── 配置 ──────────────────────────────────────────────
SERVER_URL = "ws://localhost:8900/ws/admin"
ADMIN_PANEL_URL = "http://localhost:8900/admin"
REPORT_INTERVAL = 3  # 每 3 秒上报一次状态

# ── Windows API 类型 ──────────────────────────────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


# ── 状态采集 ──────────────────────────────────────────
def get_foreground_window_title() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_foreground_app_name() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "未知"
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "未知"
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return "🔒 受保护的应用"
    try:
        buf_size = ctypes.wintypes.DWORD(512)
        buf = ctypes.create_unicode_buffer(512)
        kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_size))
        exe_path = buf.value
        exe_name = Path(exe_path).stem
        return exe_name
    except Exception:
        return "未知"
    finally:
        kernel32.CloseHandle(handle)


def get_idle_seconds() -> int:
    """获取系统空闲秒数（使用 GetTickCount64 防止49天溢出）"""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        # 使用 GetTickCount64 避免溢出
        try:
            get_tick_count_64 = kernel32.GetTickCount64
            get_tick_count_64.restype = ctypes.c_uint64
            now_ms = get_tick_count_64()
        except AttributeError:
            # Windows 7 以下回退（实际你用的是 Win10+，不会走到这里）
            now_ms = kernel32.GetTickCount() & 0xFFFFFFFF
        idle_ms = now_ms - lii.dwTime
        # 处理可能的回绕
        if idle_ms < 0:
            idle_ms += 0x100000000
        return int(idle_ms) // 1000
    return 0


# ── 应用名称美化映射 ──────────────────────────────────
APP_FRIENDLY_NAMES = {
    "Code": "VS Code",
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    "WeChat": "微信",
    "Weixin": "微信",
    "QQ": "QQ",
    "WXWork": "企业微信",
    "DingTalk": "钉钉",
    "explorer": "文件资源管理器",
    "SearchHost": "搜索",
    "ShellExperienceHost": "Shell",
    "ApplicationFrameHost": "应用",
    "firefox": "Firefox",
    "notepad": "记事本",
    "WINWORD": "Word",
    "EXCEL": "Excel",
    "POWERPNT": "PowerPoint",
    "ONENOTE": "OneNote",
    "Telegram": "Telegram",
    "Discord": "Discord",
    "Spotify": "Spotify",
    "Music.UI": "Groove 音乐",
    "vlc": "VLC",
    "PotPlayerMini64": "PotPlayer",
    "PotPlayerMini": "PotPlayer",
    "WindowsTerminal": "终端",
    "cmd": "命令提示符",
    "py": "Python",
    "python": "Python",
    "java": "Java",
    "devenv": "Visual Studio",
    "idea64": "IntelliJ IDEA",
    "webstorm64": "WebStorm",
    "WorkBuddy": "WorkBuddy",
    "Cursor": "Cursor",
    "Notion": "Notion",
    "NotionEnhanced": "Notion",
    "Obsidian": "Obsidian",
    "Figma": "Figma",
    "Steam": "Steam",
    "efind": "eFind",
}


def friendly_app_name(raw_name: str) -> str:
    if not raw_name or raw_name == "未知":
        return raw_name
    return APP_FRIENDLY_NAMES.get(raw_name, raw_name)


# ── 今日使用时长追踪 ──────────────────────────────────
today_date: str = ""
today_seconds: int = 0
last_tick: float = 0
app_times: dict[str, int] = {}  # {"VS Code": 123, "Google Chrome": 456, ...}
last_app: str = ""


def update_today_seconds(idle_secs: int, current_app: str):
    global today_date, today_seconds, last_tick, app_times, last_app
    today = date.today().isoformat()
    if today != today_date:
        today_date = today
        today_seconds = 0
        app_times = {}
    now = time.time()
    if last_tick > 0:
        delta = now - last_tick
        # 防止时钟回跳导致巨大 delta
        if delta > 0 and delta < 60:
            if idle_secs < 60:
                today_seconds += int(delta)
                # 累加到上一个应用（上一轮检测到的应用）
                if last_app and last_app != "未知" and last_app != "🔒 受保护的应用":
                    app_times[last_app] = app_times.get(last_app, 0) + int(delta)
    last_tick = now
    last_app = current_app


# ── 线程安全的托盘提示更新 ────────────────────────────
tray_icon = None
_tooltip_lock = threading.Lock()
_pending_tooltip = None


def update_tray_tooltip(text: str):
    """请求更新托盘提示文字（线程安全，通过 pystray notify 实现）"""
    global _pending_tooltip
    with _tooltip_lock:
        _pending_tooltip = text


def _apply_tooltip():
    """由 pystray 内部循环调用，实际更新 tooltip"""
    global _pending_tooltip
    with _tooltip_lock:
        text = _pending_tooltip
        _pending_tooltip = None
    if text and tray_icon:
        try:
            tray_icon.title = text
        except Exception:
            pass


# ── WebSocket 客户端 ─────────────────────────────────
async def run_client():
    while True:
        try:
            async with websockets.connect(SERVER_URL) as ws:
                update_tray_tooltip("🟢 WAID - 已连接")
                recv_task = asyncio.create_task(receive_messages(ws))
                try:
                    while True:
                        title = get_foreground_window_title()
                        app_raw = get_foreground_app_name()
                        app_name = friendly_app_name(app_raw)
                        idle_secs = get_idle_seconds()
                        update_today_seconds(idle_secs, app_name)

                        # 按使用时长排序的应用列表
                        sorted_apps = sorted(app_times.items(), key=lambda x: x[1], reverse=True)

                        status = {
                            "type": "status",
                            "data": {
                                "app": app_name,
                                "app_raw": app_raw,
                                "title": title,
                                "idle_seconds": idle_secs,
                                "today_seconds": today_seconds,
                                "online": True,
                                "app_times": sorted_apps,
                            },
                        }
                        await ws.send(json.dumps(status, ensure_ascii=False))

                        # 更新托盘提示文字
                        idle_text = "活跃" if idle_secs < 60 else f"空闲{idle_secs // 60}分钟"
                        update_tray_tooltip(f"WAID | {app_name} | {idle_text}")

                        await asyncio.sleep(REPORT_INTERVAL)
                except websockets.ConnectionClosed:
                    update_tray_tooltip("🔴 WAID - 连接断开")
                    recv_task.cancel()
                except Exception as e:
                    update_tray_tooltip(f"🔴 WAID - 错误")
                    recv_task.cancel()
        except (ConnectionRefusedError, OSError):
            update_tray_tooltip("🔴 WAID - Server未启动")
            await asyncio.sleep(5)
        except Exception:
            update_tray_tooltip("🔴 WAID - 连接错误")
            await asyncio.sleep(3)


async def receive_messages(ws):
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "chat":
                content = msg.get("data", {}).get("content", "")
                sender = msg.get("data", {}).get("sender", "")
                sender_label = "访客" if sender == "viewer" else "自己"
                # Windows 原生 Toast 通知
                try:
                    from plyer import notification
                    notification.notify(
                        title=f"💬 新消息 - {sender_label}",
                        message=content[:80],
                        app_name="What Am I Doing",
                        timeout=4,
                    )
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass


# ── 系统托盘 ──────────────────────────────────────────
def create_tray_icon():
    """创建系统托盘图标（在独立线程中运行）"""
    global tray_icon
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return

    def make_icon():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # 简洁的绿色圆点
        draw.ellipse([4, 4, 60, 60], fill=(52, 199, 89, 255))
        draw.ellipse([12, 12, 52, 52], fill=(48, 209, 88, 255))
        # 中心白色圆点
        draw.ellipse([24, 24, 40, 40], fill=(255, 255, 255, 200))
        return img

    def on_open_panel(icon, item):
        webbrowser.open(ADMIN_PANEL_URL)

    def on_quit(icon, item):
        icon.stop()
        # 用 os._exit 强制退出所有线程（包括 asyncio 事件循环）
        os._exit(0)

    icon = pystray.Icon(
        "waid",
        make_icon(),
        "WAID | 启动中...",
        menu=pystray.Menu(
            pystray.MenuItem("🖥️ 管理面板", on_open_panel, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ 退出", on_quit),
        ),
    )
    tray_icon = icon

    # 用 pystray 的 notify 机制定期应用 tooltip 更新
    def periodic_update(icon):
        _apply_tooltip()
        # 500ms 后再次调度
        icon.notify("")  # 空通知不会弹窗，但触发下一轮
        threading.Timer(0.5, periodic_update, args=(icon,)).start()

    # 启动后开始周期性更新
    threading.Timer(1.0, periodic_update, args=(icon,)).start()
    icon.run()


# ── 主入口 ────────────────────────────────────────────
def main():
    # 启动托盘图标（独立线程，阻塞式运行 pystray）
    tray_thread = threading.Thread(target=create_tray_icon, daemon=True)
    tray_thread.start()

    # 启动 WebSocket 客户端
    asyncio.run(run_client())


if __name__ == "__main__":
    main()
