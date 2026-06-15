# 轻聊 · 临时 IM 系统

纯 Python + Supabase (PostgreSQL + Storage) + WebSocket 打造的轻量化临时即时通讯系统。**无注册、无手机号**，开箱即用。

---

## 项目结构

```
InaTalk/
├── main.py                    # 入口文件
├── src/
│   ├── config.py              # 全局配置 & Supabase 客户端
│   ├── auth.py                # 用户认证（密码哈希、登录、改名）
│   ├── rooms.py               # 房间管理（创建、加入、删除、密码/背景管理）
│   ├── messages.py            # 消息管理（保存、查询、裁剪）
│   ├── files_manager.py       # 文件管理（Supabase Storage 上传/下载/清理）
│   ├── cleanup.py             # 定时清理（过期房间 & 文件）
│   ├── websocket.py           # WebSocket 连接 & 消息路由
│   └── routes.py              # HTTP 路由 & CORS 中间件
├── static/
│   ├── index.html             # 前端页面
│   ├── css/                   # 样式文件 (5个)
│   └── js/                    # 前端逻辑 (6个)
├── requirements.txt
└── README.md
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 Supabase

创建 `.env` 文件：

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

### 3. 创建数据库表

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
    last_activity DOUBLE PRECISION NOT NULL,
    background TEXT
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

### 4. 创建 Storage Bucket

在 Supabase 控制台 → **Storage** → **New bucket**：

| Bucket 名称 | 权限 | 用途 |
|------------|------|------|
| `room-files` | **private** | 聊天文件存储 |
| `room-backgrounds` | **public** | 房间背景图片 |

### 5. 启动服务

```bash
# 普通模式
python main.py

# 热更新模式（修改代码自动重启）
python main.py --dev
```

### 6. 打开前端

浏览器访问 `http://localhost:8766`

---

## 核心功能

### 用户身份

| 操作 | 说明 |
|------|------|
| 登录 | 输入**唯一用户名 + 密钥**，首次使用自动创建账号 |
| 修改用户名 | 点击 ⚙ → "修改用户名" |
| 重置密钥 | 点击 ⚙ → "重置密钥" |
| 退出登录 | 点击"退出" |

- 无手机号、无邮箱，极度隐私
- 密码使用 PBKDF2-SHA256（10 万次迭代）安全存储

### 房间系统

| 操作 | 说明 |
|------|------|
| 创建房间 | 设置房间名 + 可选密码保护 |
| 加入房间 | 搜索房间名或 8 位 ID，加密房间需密码 |
| 在线成员 | 实时显示房间内在线列表 |
| 云端存储 | 房间和消息持久化在 Supabase PostgreSQL |
| 消息限制 | 每房间最多保留 200 条上下文消息 |
| 自动清理 | 房间最后活跃超过 7 天 → 自动删除 |

### 房间管理（仅创建者）

| 操作 | 说明 |
|------|------|
| 🔑 密码管理 | 无密码时可添加密码；有密码时可修改或移除 |
| 🖼️ 背景管理 | 上传房间背景图（JPG/PNG/GIF/WebP，≤10MB）；替换时自动清理旧图 |
| 🗑️ 删除房间 | 确认后删除房间及所有消息、文件、背景 |

入口：设置 → 🛠️ 房间管理

### 文件上传

| 功能 | 说明 |
|------|------|
| 上传 | 点击 📎 按钮选择文件 |
| 大小限制 | 单文件最大 **50MB** |
| 保留时长 | 3小时 / 1天 / 7天 / 30天 / 永久 |
| 存储 | **Supabase Storage**，不占服务器磁盘 |
| 下载 | 通过签名 URL 安全下载（1小时有效） |
| 删除房间 | 云端文件随房间一并删除 |

---

## 配置说明

在 `src/config.py` 修改：

```python
HOST = "0.0.0.0"              # 监听地址
PORT = 8766                     # 服务端口
ROOM_EXPIRE_DAYS = 7            # 房间过期天数
CLEANUP_HOUR = 3                # 每天清理时间（小时）
MAX_MSG_PER_ROOM = 200          # 每房间最大消息数
MAX_FILE_SIZE = 50*1024**2     # 文件大小限制（50MB）
MAX_BG_SIZE = 10*1024**2       # 背景图大小限制（10MB）
```

---

## 技术架构

```
┌──────────────┐   WebSocket + HTTP   ┌───────────────────┐
│  static/     │ ◄──────────────────► │   src/ 模块        │
│  (前端页面)   │   同一端口 (8766)      │  (Python 后端)     │
└──────────────┘                      └───────┬───────────┘
                                              │
                                  ┌───────────┴───────────┐
                                  │       Supabase        │
                                  │  PostgreSQL + Storage │
                                  └───────────────────────┘
```

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | HTML + CSS + JS | 纯原生，零框架 |
| 通讯 | WebSocket | aiohttp，实时双向 |
| 数据库 | Supabase PostgreSQL | 用户/房间/消息/文件元数据 |
| 文件存储 | Supabase Storage | 云端对象存储，公私分离 |
| 背景存储 | Supabase Storage (public) | CDN 加速直连访问 |
| 密码 | PBKDF2-SHA256 | 10 万次迭代 + 随机盐 |

---

## WebSocket 消息协议

全部 JSON 格式，通过 `type` 字段区分：

| type | 方向 | 说明 |
|------|------|------|
| `login` | C→S | 登录/创建账号 |
| `get_rooms` | C→S | 获取房间列表 |
| `create_room` | C→S | 创建房间 |
| `join_room` | C→S | 加入房间 |
| `leave_room` | C→S | 离开房间 |
| `send_message` | C→S | 发送消息 |
| `get_files` | C→S | 获取文件列表 |
| `delete_file` | C→S | 删除文件 |
| `get_my_rooms` | C→S | 获取我创建的房间（管理用） |
| `delete_room` | C→S | 删除房间 |
| `change_room_password` | C→S | 修改/添加房间密码 |
| `remove_room_password` | C→S | 移除房间密码 |
| `update_room_background` | C→S | 更新房间背景引用 |
| `change_username` | C→S | 修改用户名 |
| `reset_password` | C→S | 重置密钥 |
| `logout` | C→S | 退出登录 |
| `login_result` | S→C | 登录结果 |
| `room_list` | S→C | 房间列表 |
| `room_joined` | S→C | 加入成功（含历史消息+背景） |
| `new_message` | S→C | 新消息广播 |
| `new_file` | S→C | 新文件广播 |
| `online_users` | S→C | 在线成员更新 |
| `system` | S→C | 系统通知 |
| `error` | S→C | 错误信息 |
