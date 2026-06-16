# 轻聊 · 临时 IM 系统

纯 Python + Supabase (PostgreSQL + Storage) + WebSocket 打造的轻量化临时即时通讯系统。**无注册、无手机号**，开箱即用。支持 Kubernetes 集群部署。

---

## 项目结构

```
ruanks/
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
├── k8s/
│   ├── base/                  # K8s 部署清单（Deployment/Service/Ingress/HPA）
│   └── overlays/              # Kustomize overlay 示例
├── Dockerfile                 # 容器镜像构建
├── deploy.sh                  # 一键部署脚本（3 节点集群）
├── requirements.txt
└── README.md
```

---

## 快速开始

### 1. 一键准备（首次）

```bash
# 克隆并安装依赖
git clone <仓库地址> && cd ruanks
pip install -r requirements.txt

# 配置环境变量（复制模板 → 填入真实值）
cp env.example .env
# 编辑 .env，填入你的 Supabase URL 和 anon key
```

> `.env` 已加入 `.gitignore`，不会提交到仓库，安全无虞。

### 2. 配置 Supabase

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

-- 表情包表（新增）
CREATE TABLE stickers (
    id SERIAL PRIMARY KEY,
    room_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
GRANT ALL ON public.stickers TO anon;
GRANT USAGE, SELECT ON SEQUENCE stickers_id_seq TO anon;
```

### 3. 创建 Storage Bucket（一次性）

在 Supabase 控制台 → **Storage** → **New bucket**：

| Bucket 名称 | 权限 | 用途 |
|------------|------|------|
| `room-files` | **private** | 聊天文件存储 |
| `room-backgrounds` | **public** | 房间背景图片 |

### 4. 启动服务

```bash
# 普通模式
python main.py

# 热更新模式（修改代码自动重启）
python main.py --dev
```

### 5. 打开前端

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
| 图片预览 | JPG/PNG/GIF/WebP 直接内联显示，左键放大灯箱 |
| 视频预览 | MP4/WebM 内联播放 |
| 存储 | **Supabase Storage**，不占服务器磁盘 |
| 下载 | 后端代理 authenticated 端点安全下载 |
| 删除房间 | 云端文件随房间一并删除 |

### 表情包（新）

| 功能 | 说明 |
|------|------|
| 上传 | 聊天栏点 😸 → "+ 上传"，选图片上传 |
| 列表 | 仅展示自己上传的表情包，永久保留 |
| 发送 | 左键点击直接发送图片到聊天 |
| 下载 | 右键弹出自定义菜单 → 下载 |
| 删除 | 鼠标悬浮表情包 → 点击 ✕ |

> 表情包存储在独立的 `stickers` 表，与附件隔离。

### 灯箱

左键点击聊天中的图片 → 全屏放大；ESC / 点击背景关闭；灯箱内 ⌄ 按钮下载原图。

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

---

## Kubernetes 部署

### 前置条件

- 3 台 Linux 节点（1 master + 2 worker），kubeadm 集群 + containerd
- 每台安装 Docker（`yum install -y docker`）
- Supabase 项目已建表（含 `stickers` 表，见上方 SQL）
- Supabase Dashboard 手动创建 Storage bucket：`room-files`（私有）、`room-backgrounds`（公开）

### 第一次部署

```bash
# 1. 代码放到每台节点的 /root/ruanks/

# 2. 三台节点构建镜像
for ip in "" 192.168.20.143 192.168.20.144; do
  ssh root@$ip "docker build --no-cache -t ruanks:latest /root/ruanks/"
done

# 3. 创建 Secret（放 .env 敏感信息）
kubectl create secret generic ruanks-env \
  --from-env-file=.env -n ruanks

# 4. 部署
kubectl apply -k k8s/base/

# 5. 缩到单副本（WebSocket 不支持多副本）
kubectl -n ruanks scale deployment ruanks --replicas=1

# 6. 确认 Pod 运行
kubectl -n ruanks get pods -w
```

### ⚠️ 部署后必做

#### a) DNS 加速（hostAliases）

K8s CoreDNS 多一层转发，Supabase API 可能巨慢甚至超时。在 Windows 查 IP 后写入 Pod hosts：

```powershell
# Windows PowerShell 查 IP
[System.Net.Dns]::GetHostAddresses("你的项目.supabase.co")
```

```bash
# K8s master 执行
kubectl patch deployment ruanks -n ruanks -p \
  '{"spec":{"template":{"spec":{"hostAliases":[{"ip":"172.64.149.246","hostnames":["xxx.supabase.co"]}]}}}}'
```

> 不写这一步登录会卡 10 秒+

#### b) 防火墙放行 NodePort

```bash
# 三台都执行（否则 NodePort 不通）
firewall-cmd --add-port=30080/tcp --permanent && firewall-cmd --reload
```

> 只在 master 放行也行，Pod 通过 kube-proxy iptables 路由

#### c) 验证

```bash
# 直接测 Pod 端口（找 Pod 所在节点）
kubectl -n ruanks get pods -o wide
ssh root@<Pod所在节点IP> "curl -s http://localhost:30080/api/health"
# 返回 {"status": "ok"} 即成功
```

### 更新部署

```bash
# Windows → master
scp D:\my_work\ruanks\src\*.py D:\my_work\ruanks\static\** root@192.168.20.137:/root/ruanks/

# master → 节点
for ip in 192.168.20.143 192.168.20.144; do
  scp /root/ruanks/src/*.py root@$ip:/root/ruanks/src/
  scp /root/ruanks/static/js/*.js root@$ip:/root/ruanks/static/js/
  scp /root/ruanks/static/css/*.css root@$ip:/root/ruanks/static/css/
done

# 三台重建镜像 + 重启 Pod
for ip in "" 192.168.20.143 192.168.20.144; do
  ssh root@$ip "docker rmi ruanks:latest 2>/dev/null; docker build --no-cache -t ruanks:latest /root/ruanks/"
done
kubectl delete pods -n ruanks --all
```

> ⚠️ 每次更新后 hostAliases 会丢失，需重新 patch

### Windows 端口转发（VMware NAT）

如果 K8s 在 VMware NAT 内，外部需通过 Windows 端口转发访问：

```powershell
# 管理员 PowerShell — 添加转发
netsh interface portproxy add v4tov4 \
  listenport=8766 listenaddress=0.0.0.0 \
  connectport=30080 connectaddress=<Pod所在节点IP>

# 查看规则
netsh interface portproxy show all

# 删除规则
netsh interface portproxy delete v4tov4 listenport=8766 listenaddress=0.0.0.0
```

### SSH 免密（省事）

```bash
ssh-keygen -t rsa -b 2048 -N '' -f ~/.ssh/id_rsa
for ip in 192.168.20.137 192.168.20.143 192.168.20.144; do
  ssh-copy-id root@$ip
done
```

### 一键脚本（包含 hostAliases）

```bash
#!/bin/bash
# 保存为 redeploy.sh
# 同步代码 → 三台重建 → 部署 + DNS 加速
for ip in 192.168.20.143 192.168.20.144; do
    scp /root/ruanks/src/*.py root@$ip:/root/ruanks/src/
    scp /root/ruanks/static/js/*.js root@$ip:/root/ruanks/static/js/
    scp /root/ruanks/static/css/*.css root@$ip:/root/ruanks/static/css/
done
for ip in "" 192.168.20.143 192.168.20.144; do
    ssh root@$ip "docker rmi ruanks:latest 2>/dev/null; docker build --no-cache -t ruanks:latest /root/ruanks/"
done
kubectl delete pods -n ruanks --all
sleep 10
kubectl -n ruanks scale deployment ruanks --replicas=1
kubectl patch deployment ruanks -n ruanks -p \
  '{"spec":{"template":{"spec":{"hostAliases":[{"ip":"172.64.149.246","hostnames":["你的项目.supabase.co"]}]}}}}'
echo "✅ 部署完成"
```

### 注意事项

| 项目 | 说明 |
|------|------|
| Session Token | 内存态，重启 Pod 丢失；前端自动降级密码登录，慢一次 |
| Storage Bucket | 须在 Supabase Dashboard **手动创建**，anon key 无创建权限 |
| 多副本 | **必须单副本**，WebSocket 不支持多实例路由 |
| hostAliases | 每次更新丢失，需重新 patch；或写入部署 YAML 的 template.spec |
| 端口转发 | Windows `netsh portproxy` 规则是持久的，重启不丢 |

## 集群容灾 & 高可用

### 架构优势

| 特性 | 说明 |
|------|------|
| 无状态服务 | 所有业务数据存 Supabase，K8s 节点仅跑计算 + 转发，Pod 重启不丢数据 |
| 自愈 | 节点宕机后 30s 内 K8s 将 Pod 自动调度到健康节点 |
| 滚动更新 | `kubectl set image` 零停机更新，旧 Pod 处理完请求后新 Pod 上线 |
| 数据持久 | Supabase PostgreSQL 每日自动备份，文件存储于 S3 兼容 Storage |

### 集群优势演示

#### 演示1：手动杀 Pod（自愈）

```bash
# 终端1：观察 Pod 状态
kubectl -n ruanks get pods -w

# 终端2：暴力删除 Pod
kubectl -n ruanks delete pod <pod名> --grace-period=0

# 结果：3-5 秒自动拉起新 Pod，前端 WebSocket 自动重连，消息不丢
```

#### 演示2：节点宕机（漂移）

```bash
# 模拟 node2 崩溃
ssh root@192.168.20.144 "shutdown -h now"

# master 观察
kubectl get nodes                          # node2 → NotReady
kubectl -n ruanks get pods -o wide          # Pod 自动漂移到 node1
# ~30 秒恢复，前端短暂断连后重连成功
```

#### 演示3：滚动更新（零停机）

```bash
# 改镜像后更新
kubectl set image deployment/ruanks ruanks=ruanks:v2
# 前端持续发消息，旧 Pod 处理完后新 Pod 启动，无中断
```

### 性能基准

| 指标 | 数值 | 说明 |
|------|------|------|
| 并发在线 | ~200-500 人 | Python aiohttp 单进程 + WebSocket 长连接 |
| 单条消息延迟 | <50ms | 纯内存广播，不等待 DB |
| 1000 条消息 | <1 秒 | 异步非阻塞 |
| 水平扩展 | 不支持 | WebSocket 单副本运行（多副本需引入 Redis 消息总线） |

### 扩展路线

```
当前:  单 Pod → NodePort → aiohttp WebSocket
目标1: + Redis Pub/Sub  → 多副本广播
目标2: + HPA             → 按 CPU/连接数自动扩缩
目标3: + Ingress         → 域名 + TLS + sticky session
```

---

## 已知问题

| 问题 | 状态 |
|------|------|
| K8s 多副本 WebSocket 路由不一致 | 🟡 已规避 — 单副本运行，后续需 Ingress sticky session |
| Supabase Storage 中文文件名报错 | ✅ 已修复 — storage_key 改用 UUID + 扩展名 |
