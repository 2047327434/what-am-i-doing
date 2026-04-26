# 🖥️ What Am I Doing

实时展示电脑使用状态的小工具，让别人知道你正在做什么。

## 架构

```
┌─────────────────┐     WebSocket      ┌──────────────┐     WebSocket     ┌──────────────┐
│  Admin 客户端    │ ◄──────────────► │    Server     │ ◄─────────────► │  用户前端      │
│  (Python 常驻)   │   状态上报/消息    │  (FastAPI)    │   状态推送/聊天   │  (HTML/JS)    │
└─────────────────┘                    └──────────────┘                   └──────────────┘
```

- **Server** — FastAPI + WebSocket + SQLite，负责状态中转、消息持久化、前端托管
- **Admin 客户端** — Python 常驻托盘，采集前台应用名/窗口标题/空闲时长/使用时长，WebSocket 上报
- **用户前端** — 玻璃态 UI，实时状态展示 + 应用使用排行 + 聊天
- **Admin 面板** — `/admin` 管理面板，实时监控 + 聊天回复

## 功能

- 🖥️ 实时显示当前使用的应用名称
- ⏱️ 今日累计使用时长（自动区分活跃/空闲）
- 📊 应用使用时间排行（按使用时长排序）
- 💬 访客与 Admin 实时聊天
- 🔔 访客消息 Windows Toast 通知
- 🟢 系统托盘常驻（无控制台窗口）

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows

# 安装 Server 依赖
pip install -r server/requirements.txt

# 安装 Admin 客户端依赖
pip install -r admin/requirements.txt
```

### 2. 启动

```bash
# 方式一：一键启动
start.bat

# 方式二：手动启动
# 终端1 - 启动 Server
python server/main.py

# 终端2 - 启动 Admin 客户端（无窗口模式）
pythonw admin/client.py
```

### 3. 访问

| 地址 | 说明 |
|------|------|
| `http://localhost:8900/` | 用户端 |
| `http://localhost:8900/admin` | 管理面板 |

## 部署到服务器

将 Server 部署到公网服务器，Admin 客户端修改 `SERVER_URL` 指向公网地址即可：

```python
# admin/client.py
SERVER_URL = "wss://your-domain.com/ws/admin"
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Server | FastAPI + WebSocket + SQLite + aiosqlite |
| Admin 客户端 | Python + ctypes + pystray + plyer + websockets |
| 用户前端 | HTML + CSS (Glassmorphism) + 原生 WebSocket |
| 部署 | Docker / 宝塔面板 |

## License

MIT
