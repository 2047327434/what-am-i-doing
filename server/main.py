"""
What Am I Doing - Server
FastAPI + WebSocket + SQLite
"""
import asyncio
import json
import time
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── 配置 ──────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "data" / "waid.db"
WEB_DIR = Path(__file__).parent.parent / "web"

# ── 全局状态 ──────────────────────────────────────────
admin_ws: WebSocket | None = None        # Admin Python客户端的 WebSocket 连接
admin_panel_ws_list: list[WebSocket] = [] # Admin WebUI 面板的 WebSocket 连接
viewer_ws_list: list[WebSocket] = []     # 所有用户端 WebSocket
latest_status: dict = {                  # Admin 最新上报的状态
    "app": "离线",
    "title": "",
    "idle_seconds": 0,
    "today_seconds": 0,
    "online": False,
    "last_heartbeat": 0,
    "app_times": [],
}

# ── 数据库 ────────────────────────────────────────────
async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,        -- 'admin' | 'viewer'
                content TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        await db.commit()


async def save_message(sender: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, ?)",
            (sender, content, time.time()),
        )
        await db.commit()


async def load_recent_messages(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT sender, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


# ── FastAPI App ───────────────────────────────────────
app = FastAPI(title="What Am I Doing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件 (web 前端)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/admin")
async def admin_panel():
    return FileResponse(str(WEB_DIR / "admin.html"))


# ── REST API ──────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    """获取 Admin 最新状态（对外隐藏内部字段）"""
    if latest_status["online"] and time.time() - latest_status["last_heartbeat"] > 30:
        latest_status["online"] = False
        latest_status["app"] = "离线"
    return {
        "app": latest_status["app"],
        "title": latest_status["title"],
        "idle_seconds": latest_status["idle_seconds"],
        "today_seconds": latest_status["today_seconds"],
        "online": latest_status["online"],
        "app_times": latest_status["app_times"],
    }


@app.get("/api/messages")
async def get_messages():
    """获取最近聊天记录"""
    return await load_recent_messages()


# ── WebSocket: Admin Python 客户端连接 ───────────────
@app.websocket("/ws/admin")
async def ws_admin(ws: WebSocket):
    """Admin Python客户端专用 - 只负责上报状态和接收消息通知"""
    global admin_ws, latest_status
    await ws.accept()
    admin_ws = ws
    latest_status["online"] = True
    latest_status["last_heartbeat"] = time.time()
    print(f"[Server] Admin 客户端已连接 {ws.client}")

    # 通知所有用户端和 Admin 面板
    await broadcast_to_viewers({"type": "status", "data": build_public_status()})
    await broadcast_to_admin_panels({"type": "status", "data": build_public_status()})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "status":
                data = msg.get("data", {})
                # 只更新允许的字段，不覆盖 last_heartbeat 等内部字段
                for key in ("app", "app_raw", "title", "idle_seconds", "today_seconds", "app_times"):
                    if key in data:
                        latest_status[key] = data[key]
                latest_status["online"] = True
                latest_status["last_heartbeat"] = time.time()
                public = build_public_status()
                await broadcast_to_viewers({"type": "status", "data": public})
                await broadcast_to_admin_panels({"type": "status", "data": public})

    except WebSocketDisconnect:
        print("[Server] Admin 客户端已断开")
    except Exception as e:
        print(f"[Server] Admin 客户端异常: {e}")
    finally:
        if admin_ws is ws:
            admin_ws = None
            latest_status["online"] = False
            latest_status["app"] = "离线"
            public = build_public_status()
            await broadcast_to_viewers({"type": "status", "data": public})
            await broadcast_to_admin_panels({"type": "status", "data": public})


# ── WebSocket: Admin WebUI 面板连接 ──────────────────
@app.websocket("/ws/admin-panel")
async def ws_admin_panel(ws: WebSocket):
    """Admin WebUI 面板 - 可以看状态、收发消息"""
    await ws.accept()
    admin_panel_ws_list.append(ws)
    print(f"[Server] Admin 面板已连接 {ws.client}")

    # 先发一次当前状态
    await safe_send(ws, {"type": "status", "data": build_public_status()})

    # 发送历史消息
    history = await load_recent_messages()
    if history:
        await safe_send(ws, {"type": "history", "data": history})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "chat":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                await save_message("admin", content)
                chat_msg = {
                    "type": "chat",
                    "data": {
                        "sender": "admin",
                        "content": content,
                        "timestamp": time.time(),
                    },
                }
                await broadcast_to_viewers(chat_msg)
                await broadcast_to_admin_panels(chat_msg)
                # 不再转发给 Admin Python 客户端——admin 自己回的消息无需弹通知

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Server] Admin 面板异常: {e}")
    finally:
        if ws in admin_panel_ws_list:
            admin_panel_ws_list.remove(ws)
        print(f"[Server] Admin 面板已断开, 剩余 {len(admin_panel_ws_list)} 个")


# ── WebSocket: 用户端连接 ────────────────────────────
@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
    await ws.accept()
    viewer_ws_list.append(ws)
    print(f"[Server] 用户端已连接 {ws.client}, 共 {len(viewer_ws_list)} 人")

    # 先发一次当前状态
    await safe_send(ws, {"type": "status", "data": build_public_status()})

    # 发送历史消息
    history = await load_recent_messages()
    if history:
        await safe_send(ws, {"type": "history", "data": history})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "chat":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                await save_message("viewer", content)
                chat_msg = {
                    "type": "chat",
                    "data": {
                        "sender": "viewer",
                        "content": content,
                        "timestamp": time.time(),
                    },
                }
                # 转发给 Admin Python 客户端
                if admin_ws:
                    await safe_send(admin_ws, chat_msg)
                # 广播给所有 Admin 面板
                await broadcast_to_admin_panels(chat_msg)
                # 广播给所有用户端
                await broadcast_to_viewers(chat_msg)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Server] 用户端异常: {e}")
    finally:
        if ws in viewer_ws_list:
            viewer_ws_list.remove(ws)
        print(f"[Server] 用户端已断开, 剩余 {len(viewer_ws_list)} 人")


# ── 工具函数 ──────────────────────────────────────────
def build_public_status() -> dict:
    """构建对外暴露的状态（过滤内部字段）"""
    return {
        "app": latest_status["app"],
        "title": latest_status["title"],
        "idle_seconds": latest_status["idle_seconds"],
        "today_seconds": latest_status["today_seconds"],
        "online": latest_status["online"],
        "app_times": latest_status["app_times"],
    }


async def safe_send(ws: WebSocket, msg: dict):
    """安全发送 WebSocket 消息，异常不抛出"""
    try:
        await ws.send_text(json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass


async def broadcast_to_viewers(msg: dict):
    text = json.dumps(msg, ensure_ascii=False)
    disconnected = []
    for ws in viewer_ws_list:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in viewer_ws_list:
            viewer_ws_list.remove(ws)


async def broadcast_to_admin_panels(msg: dict):
    text = json.dumps(msg, ensure_ascii=False)
    disconnected = []
    for ws in admin_panel_ws_list:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in admin_panel_ws_list:
            admin_panel_ws_list.remove(ws)


# ── 启动 ──────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()
    print("[Server] 数据库初始化完成")
    print("[Server] 启动成功 → http://localhost:8900")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8900)
