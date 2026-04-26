# 🖥️ What Am I Doing

实时展示电脑使用状态的轻量工具。Admin 客户端采集前台窗口信息，通过 WebSocket 推送到 Web 前端，让访客知道你正在做什么。

## ✨ 功能特性

- 🖥️ **实时状态** — 显示当前使用的应用名称和窗口标题
- ⏱️ **使用时长** — 今日累计使用时长，自动区分活跃/空闲
- 📊 **应用排行** — 按使用时长排序的应用排行，精确到分秒
- 💬 **实时聊天** — 访客与 Admin 双向聊天
- 🔔 **消息通知** — 访客消息自动弹 Windows Toast 通知
- 🟢 **托盘常驻** — 无控制台窗口，系统托盘后台运行
- 🪟 **玻璃态 UI** — iOS 风格毛玻璃界面

## 📸 截图

| 用户端 | 管理面板 |
|--------|----------|
| 用户查看实时状态 + 聊天 | 监控状态 + 回复访客消息 |

## 架构

```
┌─────────────────┐     WebSocket      ┌──────────────┐     WebSocket     ┌──────────────┐
│  Admin 客户端    │ ◄──────────────► │    Server     │ ◄─────────────► │  用户前端      │
│  (Python 常驻)   │   状态上报/消息    │  (FastAPI)    │   状态推送/聊天   │  (HTML/JS)    │
└─────────────────┘                    └──────────────┘                   └──────────────┘
                                              ▲
                                              │ WebSocket
                                              │
                                       ┌──────────────┐
                                       │  Admin 面板   │
                                       │  (/admin)     │
                                       └──────────────┘
```

| 组件 | 说明 |
|------|------|
| **Server** | FastAPI + WebSocket + SQLite，负责状态中转、消息持久化、前端静态托管 |
| **Admin 客户端** | Python 常驻托盘，采集前台应用名/窗口标题/空闲时长/使用时长，WebSocket 上报 |
| **用户前端** | 玻璃态 UI，实时状态展示 + 应用排行 + 聊天 |
| **Admin 面板** | `/admin` 管理面板，实时监控 + 聊天回复 |

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/2047327434/what-am-i-doing.git
cd what-am-i-doing
```

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows

# 安装 Server 依赖
pip install -r server/requirements.txt

# 安装 Admin 客户端依赖
pip install -r admin/requirements.txt
```

<details>
<summary>📦 依赖详情</summary>

**Server** (`server/requirements.txt`):
- `fastapi>=0.104.0` — Web 框架
- `uvicorn>=0.24.0` — ASGI 服务器
- `aiosqlite>=0.19.0` — 异步 SQLite
- `websockets>=12.0` — WebSocket

**Admin 客户端** (`admin/requirements.txt`):
- `websockets>=12.0` — WebSocket 通信
- `pystray>=0.19.0` — 系统托盘
- `Pillow>=10.0.0` — 托盘图标
- `plyer>=2.1.0` — Windows Toast 通知
</details>

### 3. 启动

```bash
# 方式一：一键启动（Windows）
start.bat

# 方式二：手动启动
# 终端1 - 启动 Server
python server/main.py

# 终端2 - 启动 Admin 客户端（无窗口模式）
pythonw admin/client.py
```

### 4. 访问

| 地址 | 说明 |
|------|------|
| `http://localhost:8900/` | 用户端 — 查看状态 + 聊天 |
| `http://localhost:8900/admin` | 管理面板 — 监控 + 回复 |

## 🌐 部署到服务器

将 Server 部署到公网服务器后，Admin 客户端修改 `SERVER_URL` 指向公网地址即可远程上报：

```python
# admin/client.py
SERVER_URL = "wss://your-domain.com/ws/admin"
```

Server 端推荐使用 Nginx 反向代理，配置 WebSocket 支持：

```nginx
location / {
    proxy_pass http://127.0.0.1:8900;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

## 📁 项目结构

```
what-am-i-doing/
├── server/
│   ├── main.py              # FastAPI 服务端
│   └── requirements.txt     # Server 依赖
├── admin/
│   ├── client.py            # Admin 客户端（状态采集 + 托盘）
│   └── requirements.txt     # Admin 客户端依赖
├── web/
│   ├── index.html           # 用户端前端
│   └── admin.html           # 管理面板前端
├── start.bat                # 一键启动脚本
├── stop.bat                 # 一键停止脚本
└── README.md
```

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| Server | FastAPI + WebSocket + SQLite + aiosqlite |
| Admin 客户端 | Python + ctypes + pystray + plyer + websockets |
| 用户前端 | HTML + CSS (Glassmorphism) + 原生 WebSocket |
| 部署 | Nginx 反向代理 / Docker / 宝塔面板 |

## ⚠️ 注意事项

- Admin 客户端仅支持 **Windows**（依赖 `ctypes.windll` 采集窗口信息）
- Server 和用户前端跨平台，可部署在任意系统
- 数据库文件存储在 `server/data/waid.db`，已通过 `.gitignore` 排除

## 📄 License

MIT
