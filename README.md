# 轻聊 · 临时 IM 系统

纯 Python + Supabase (PostgreSQL) + WebSocket 打造的轻量化临时即时通讯系统。**无注册、无手机号**，开箱即用。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`websockets`、`httpx`、`aiohttp`、`python-dotenv`。

### 2. 配置 Supabase

创建 `.env` 文件：

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

在 Supabase SQL Editor 中执行以下建表语句（**复制全部一次性执行**）：

```sql
-- 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

-- 房间表
CREATE TABLE rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT,
    salt TEXT,
    creator TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    last_activity DOUBLE PRECISION NOT NULL
);

-- 消息表
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    room_id TEXT NOT NULL,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    msg_type TEXT DEFAULT 'text',
    created_at DOUBLE PRECISION NOT NULL
);

-- 文件表
CREATE TABLE files (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    file_type TEXT DEFAULT 'application/octet-stream',
    uploaded_by TEXT NOT NULL,
    retention TEXT NOT NULL,
    expires_at DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL,
    storage_path TEXT NOT NULL
);

-- 关掉 RLS（鉴权由服务端处理）
ALTER TABLE users    DISABLE ROW LEVEL SECURITY;
ALTER TABLE rooms    DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE files    DISABLE ROW LEVEL SECURITY;

-- 授权 anon 角色
GRANT SELECT, INSERT, UPDATE, DELETE ON public.users    TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.rooms    TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.messages TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.files    TO anon;
```

### 3. 启动服务端

```bash
python server.py
```

启动后输出：

```
[服务] 数据库: Supabase (https://xxx.supabase.co)
[服务] 房间过期时间: 7 天
[服务] 每房间消息上限: 200 条
[服务] 文件大小限制: 4GB
[服务] 文件保留选项: 3h, 1d, 7d, 30d, forever
[服务] HTTP 文件服务启动于 http://0.0.0.0:8766
[服务] WebSocket 启动于 ws://0.0.0.0:8765
```

### 4. 打开前端

直接用浏览器打开 `index.html`，或部署到任意 Web 服务器。

> 如果通过局域网访问，修改 `app.js` 中的 `WS_URL` 和 `HTTP_URL` 为实际 IP。

---

## 核心功能

### 用户身份

| 操作 | 说明 |
|------|------|
| 登录 | 输入**唯一用户名 + 密钥**，首次使用自动创建账号 |
| 修改用户名 | 点击 ⚙ → "修改用户名"，输入新名字 + 当前密钥验证，密钥不变 |
| 重置密钥 | 点击 ⚙ → "重置密钥"，验证当前密钥后设置新密钥 |
| 退出登录 | 点击"退出"，清除本地信息 |

- 无手机号、无邮箱，极度隐私
- 用户名全局唯一（不可重复）
- 密码使用 PBKDF2-SHA256（10 万次迭代）安全存储

### 房间系统

| 操作 | 说明 |
|------|------|
| 创建房间 | 设置房间名 + 可选密码保护 |
| 加入房间 | 输入 8 位房间 ID，如有密码需输入 |
| 云端存储 | 房间和消息持久化在 Supabase PostgreSQL |
| 消息限制 | 每房间最多保留 200 条上下文消息 |
| 自动清理 | 房间最后活跃超过 7 天 → 自动删除（含消息和文件） |

### 聊天功能

- 文字消息（支持回车发送，Shift+Enter 换行）
- 30+ 基础表情（点击 😊 按钮选择）
- 实时显示在线成员列表
- 消息云端保存（每房间限 200 条）

### 文件上传（新增）

| 功能 | 说明 |
|------|------|
| 上传 | 点击 📎 按钮选择文件，支持任意格式 |
| 大小限制 | 单文件最大 **4GB** |
| 保留时长 | 3小时 / 1天 / 7天 / 30天 / 永久 |
| 下载 | 文件消息气泡中直接下载，也可在 📁 文件面板查看所有文件 |
| 删除 | 上传者可在文件面板中删除文件 |
| 自动清理 | 文件过期自动删除；房间过期则文件一并清除 |

### 自动清理

- 每天凌晨 3 点执行定时任务
- 最后活跃 > 7 天的房间自动删除（含消息 + 文件）
- 过期文件（超过保留时长）自动清理
- 可在 `server.py` 顶部修改配置

---

## 配置说明

在 `server.py` 文件顶部可修改：

```python
WS_HOST = "0.0.0.0"            # WebSocket 监听地址
WS_PORT = 8765                 # WebSocket 端口
HTTP_PORT = 8766               # HTTP 文件服务端口
ROOM_EXPIRE_DAYS = 7           # 房间过期天数
CLEANUP_HOUR = 3               # 每天清理时间（小时）
CLEANUP_MINUTE = 0             # 每天清理时间（分钟）
MAX_MSG_PER_ROOM = 200         # 每房间最大消息数
MAX_FILE_SIZE = 4*1024**3      # 文件大小限制（4GB）
```

---

## 界面操作流程

```
打开页面
  │
  ├─ 输入唯一用户名 + 密钥
  │    ├─ 首次 → 自动创建账号
  │    └─ 已有 → 验证密钥
  │
  ├─ 进入大厅
  │    ├─ 创建房间（设定名称 + 可选密码）
  │    └─ 加入已有房间（输入房间 ID + 密码）
  │
  ├─ 进入聊天室
  │    ├─ 发送文字 / 表情
  │    ├─ 📎 上传文件（选择保留时长）
  │    ├─ 📁 查看共享文件面板（下载/删除）
  │    ├─ 查看在线成员
  │    └─ 点击 ⚙ → 修改用户名 / 重置密钥
  │
  └─ 关闭页面 → 房间仍在云端
       └─ 长时间无消息 → 7 天后自动清理
```

---

## 技术架构

```
┌──────────────┐   WebSocket (8765)    ┌────────────────┐
│  index.html  │ ◄───────────────────► │   server.py    │
│  (前端页面)   │   JSON 消息协议        │  (Python 后端)  │
│              │                       │                │
│              │   HTTP (8766)         │                │
│              │ ◄── 文件上传/下载 ───► │                │
└──────────────┘                       └───────┬────────┘
                                               │
                                         ┌─────▼────┐
                                         │ Supabase  │
                                         │(PostgreSQL)│
                                         └───────────┘
```

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | HTML + CSS + JS | 纯原生，零框架 |
| 通讯 | WebSocket | `websockets` 库，实时双向通讯 |
| 文件 | HTTP | `aiohttp` 库，端口 8766 |
| 存储 | Supabase (PostgreSQL) | 云端数据库，持久化 |
| 密码 | PBKDF2-SHA256 | `hashlib` 内置，10 万次迭代 + 随机盐 |
| 并发 | asyncio | 异步 I/O，单进程高效处理 |

---

## WebSocket 消息协议

全部 JSON 格式，通过 `type` 字段区分：

### 客户端 → 服务端

| type | 字段 | 说明 |
|------|------|------|
| `login` | `username`, `password` | 登录/创建账号 |
| `get_rooms` | — | 获取房间列表 |
| `create_room` | `name`, `password`(可选) | 创建房间 |
| `join_room` | `room_id`, `password`(可选) | 加入房间 |
| `leave_room` | — | 离开当前房间 |
| `send_message` | `room_id`, `content`, `msg_type` | 发送消息 |
| `get_files` | — | 获取文件列表 |
| `delete_file` | `file_id` | 删除文件 |
| `change_username` | `new_username`, `password` | 修改用户名 |
| `reset_password` | `old_password`, `new_password` | 重置密钥 |
| `logout` | — | 退出登录 |

### 服务端 → 客户端

| type | 说明 |
|------|------|
| `login_result` | 登录结果 |
| `room_list` | 房间列表 |
| `create_room_result` | 创建房间结果 |
| `room_joined` | 成功加入房间（含历史消息） |
| `new_message` | 新消息广播 |
| `new_file` | 新文件广播 |
| `file_list` | 文件列表 |
| `file_deleted` | 文件已删除 |
| `system` | 系统消息（加入/离开/改名） |
| `online_users` | 在线成员列表 |
| `change_username_result` | 改名结果 |
| `reset_password_result` | 重置密钥结果 |
| `room_left` | 已离开房间 |
| `logout_result` | 退出结果 |
| `error` | 错误信息 |

---

## 数据存储

所有数据存储在 Supabase PostgreSQL 中，包含四张表：

- **users** — 用户名、密码哈希、盐值
- **rooms** — 房间 ID、名称、密码哈希、创建者、最后活跃时间
- **messages** — 消息内容、发送者、房间 ID、类型、时间（每房间限 200 条）
- **files** — 文件元数据（ID、文件名、大小、保留时长、过期时间、存储路径）

---

## 常见问题

**Q: 忘记密钥怎么办？**
A: 当前版本无找回密码功能。需要在 Supabase 中手动处理或重新创建账号。

**Q: 能同时登录多个设备吗？**
A: 可以。同一用户名可在多个浏览器标签页/设备登录，消息会同步广播。

**Q: 消息保存多久？**
A: 每房间最多保留 200 条消息，超出自动删除旧消息。房间过期后所有消息清空。

**Q: 文件保存多久？**
A: 上传时可选择保留时长（3小时/1天/7天/30天/永久）。即使文件未过期，房间过期后文件也会一并清除。

**Q: 文件上传大小限制？**
A: 单文件最大 4GB。

**Q: 如何修改过期时间？**
A: 编辑 `server.py` 顶部的 `ROOM_EXPIRE_DAYS` 等配置项，重启服务生效。

**Q: 支持部署到公网吗？**
A: 可以。在服务器上运行 `python server.py`，前端修改 `WS_URL` 和 `HTTP_URL` 即可。如需 HTTPS，建议配合 Nginx 反向代理 WSS 和 HTTPS。
