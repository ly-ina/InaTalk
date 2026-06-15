// ============ 配置 ============
// 自动适配：本地开发 / K8s 部署，WebSocket 与 HTTP 同端口
const BASE = location.origin;                       // http://host:port
const WS_URL = BASE.replace(/^http/, "ws") + "/ws"; // ws://host:port/ws
const HTTP_URL = BASE;                              // http://host:port

// ============ 全局状态 ============
let ws = null;
let currentUser = null;
let currentRoom = null;
let reconnectTimer = null;
let roomFiles = [];

// ============ 表情列表 ============
const EMOJIS = ['😀','😂','🤣','😍','🥰','😎','🤩','😇','🤗','😋','😜','🤔','😤','😢','😡','👍','👎','👏','🙌','💪','🎉','🔥','❤️','💔','⭐','✅','❌','💯','🙏','🤝','🍕','☕','🐱','🐶','🦊'];

// ============ 视图切换 ============
function showView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const views = { login: 'loginView', lobby: 'lobbyView', chat: 'chatView' };
    const viewEl = document.getElementById(views[name]);
    if (viewEl) viewEl.classList.add('active');
    document.getElementById('header').style.display = name === 'login' ? 'none' : 'flex';
}

// ============ WebSocket ============
function connectWS() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
        console.log('[WS] 已连接');
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (currentUser) {
            // 重连后重新登录
            ws.send(JSON.stringify({ type: 'login', username: currentUser, password: sessionStorage.getItem('im_pass') || '' }));
        }
    };
    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            handleMessage(msg);
        } catch (err) { console.error('消息解析失败:', err); }
    };
    ws.onclose = () => {
        console.log('[WS] 断开，3秒后重连...');
        reconnectTimer = setTimeout(connectWS, 3000);
    };
    ws.onerror = () => { ws.close(); };
}

function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

// ============ 消息处理 ============
function handleMessage(msg) {
    switch (msg.type) {
        case 'login_result':
            if (msg.success) {
                currentUser = sessionStorage.getItem('im_user') || '';
                document.getElementById('currentUserLabel').textContent = currentUser;
                document.getElementById('loginError').textContent = '';
                document.getElementById('loginSuccess').textContent = msg.is_new ? '🎉 账号已创建，登录成功！' : '✅ 登录成功！';
                setTimeout(() => {
                    showView('lobby');
                    refreshRooms();
                    document.getElementById('loginSuccess').textContent = '';
                }, 600);
            } else {
                document.getElementById('loginError').textContent = msg.message;
                document.getElementById('loginBtn').disabled = false;
            }
            break;
        case 'room_list':
            allRoomsCache = msg.rooms || [];
            renderRoomList(allRoomsCache);
            break;
        case 'create_room_result':
            if (msg.success) {
                closeModal('createRoomModal');
                refreshRooms();
                // 自动加入
                joinRoomById(msg.room.id, msg.room.has_password ? document.getElementById('createRoomPass').value : '');
            } else {
                document.getElementById('createRoomError').textContent = msg.message;
            }
            break;
        case 'join_room_result':
            if (!msg.success) {
                document.getElementById('joinRoomError').textContent = msg.message;
            }
            break;
        case 'room_joined':
            currentRoom = msg.room;
            document.getElementById('chatRoomName').textContent = msg.room.name;
            document.getElementById('chatRoomId').textContent = 'ID: ' + msg.room.id;
            document.getElementById('chatMessages').innerHTML = '';
            if (msg.messages) msg.messages.forEach(m => appendMessage(m));
            scrollToBottom();
            showView('chat');
            document.getElementById('chatInput').focus();
            break;
        case 'new_message':
            appendMessage(msg);
            scrollToBottom();
            break;
        case 'system':
            appendSystem(msg.content);
            scrollToBottom();
            break;
        case 'online_users':
            renderMembers(msg.users);
            break;
        case 'room_left':
            currentRoom = null;
            showView('lobby');
            refreshRooms();
            break;
        case 'logout_result':
            currentUser = null;
            currentRoom = null;
            showView('login');
            break;
        case 'error':
            alert(msg.message);
            break;
        case 'change_username_result':
            if (msg.success) {
                currentUser = msg.new_username;
                sessionStorage.setItem('im_user', msg.new_username);
                document.getElementById('currentUserLabel').textContent = currentUser;
                document.getElementById('changeUsernameSuccess').textContent = msg.message;
                document.getElementById('changeUsernameError').textContent = '';
                document.getElementById('changeUserPass').value = '';
                document.getElementById('newUsername').value = '';
                // 如果在大厅，刷新房间列表
                if (!currentRoom) refreshRooms();
                setTimeout(() => { closeModal('changeUsernameModal'); document.getElementById('changeUsernameSuccess').textContent = ''; }, 1500);
            } else {
                document.getElementById('changeUsernameError').textContent = msg.message;
            }
            break;
        case 'reset_password_result':
            if (msg.success) {
                sessionStorage.setItem('im_pass', document.getElementById('newPassword').value);
                document.getElementById('resetPasswordSuccess').textContent = msg.message;
                document.getElementById('resetPasswordError').textContent = '';
                document.getElementById('oldPassword').value = '';
                document.getElementById('newPassword').value = '';
                setTimeout(() => { closeModal('resetPasswordModal'); document.getElementById('resetPasswordSuccess').textContent = ''; }, 1500);
            } else {
                document.getElementById('resetPasswordError').textContent = msg.message;
            }
            break;
        // --- 文件相关 ---
        case 'file_list':
            roomFiles = msg.files || [];
            renderFileList();
            break;
        case 'new_file':
            appendFileMessage(msg.file);
            scrollToBottom();
            // 自动刷新文件列表
            if (currentRoom) send({ type: 'get_files' });
            break;
        case 'file_deleted':
            roomFiles = roomFiles.filter(f => f.id !== msg.file_id);
            renderFileList();
            // 从消息列表中移除对应的文件消息
            const fileMsg = document.querySelector(`.file-msg[data-file-id="${msg.file_id}"]`);
            if (fileMsg) fileMsg.remove();
            break;
        case 'delete_file_result':
            break;
        case 'my_rooms_list':
            renderMyRooms(msg.rooms || []);
            break;
        case 'delete_room_result':
            if (msg.success) {
                document.getElementById('deleteRoomError').textContent = '';
                // 刷新我的房间列表和公共房间列表
                send({ type: 'get_my_rooms' });
                refreshRooms();
                // 如果当前在被删除的房间中，返回大厅
                if (currentRoom && currentRoom.id === msg.room_id) {
                    currentRoom = null;
                    showView('lobby');
                    refreshRooms();
                }
            } else {
                document.getElementById('deleteRoomError').textContent = msg.message;
            }
            break;
    }
}

// ============ 登录 ============
function doLogin() {
    const user = document.getElementById('loginUser').value.trim();
    const pass = document.getElementById('loginPass').value.trim();
    const errEl = document.getElementById('loginError');
    const btn = document.getElementById('loginBtn');
    errEl.textContent = '';
    if (!user || !pass) { errEl.textContent = '用户名和密钥不能为空'; return; }
    btn.disabled = true;
    btn.textContent = '登录中...';
    sessionStorage.setItem('im_user', user);
    sessionStorage.setItem('im_pass', pass);
    connectWS();
    // 等连接建立后发送登录
    const tryLogin = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            send({ type: 'login', username: user, password: pass });
        } else if (ws && ws.readyState === WebSocket.CONNECTING) {
            setTimeout(tryLogin, 200);
        } else {
            errEl.textContent = '无法连接服务器';
            btn.disabled = false;
            btn.textContent = '登 录';
        }
    };
    tryLogin();
}

document.getElementById('loginPass').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
});

// ============ 退出 ============
function logout() {
    send({ type: 'logout' });
    sessionStorage.removeItem('im_user');
    sessionStorage.removeItem('im_pass');
    currentUser = null;
    currentRoom = null;
    showView('login');
    document.getElementById('loginBtn').disabled = false;
    document.getElementById('loginBtn').textContent = '登 录';
    document.getElementById('loginUser').value = '';
    document.getElementById('loginPass').value = '';
}

// ============ 房间列表 ============
function refreshRooms() {
    send({ type: 'get_rooms' });
}

function renderRoomList(rooms) {
    const el = document.getElementById('roomList');
    if (!rooms.length) {
        el.innerHTML = '<div class="room-empty">还没有房间，创建一个吧 👆</div>';
        return;
    }
    el.innerHTML = rooms.map(r => `
        <div class="room-card" onclick="clickRoom('${r.id}', '${escHtml(r.name)}', ${r.has_password})">
            <div class="room-info">
                <div class="room-name">${escHtml(r.name)} ${r.has_password ? '🔒' : ''}</div>
                <div class="room-meta">创建者: ${escHtml(r.creator)}</div>
            </div>
            <span class="room-badge">${r.id}</span>
        </div>
    `).join('');
}

// ============ 点击房间（大厅列表） ============
function clickRoom(roomId, roomName, hasPassword) {
    if (hasPassword) {
        promptRoomPassword(roomId, roomName);
    } else {
        joinRoomById(roomId, '');
    }
}

// ============ 创建房间 ============
function showCreateRoomModal() {
    document.getElementById('createRoomName').value = '';
    document.getElementById('createRoomPass').value = '';
    document.getElementById('createRoomError').textContent = '';
    document.getElementById('createRoomModal').classList.add('active');
    document.getElementById('createRoomName').focus();
}

function doCreateRoom() {
    const name = document.getElementById('createRoomName').value.trim();
    const pass = document.getElementById('createRoomPass').value.trim();
    if (!name) { document.getElementById('createRoomError').textContent = '房间名不能为空'; return; }
    send({ type: 'create_room', name, password: pass });
}

// ============ 加入房间 ============
let allRoomsCache = [];

function showJoinRoomModal() {
    document.getElementById('joinRoomSearch').value = '';
    document.getElementById('joinRoomError').textContent = '';
    document.getElementById('roomSearchList').innerHTML = '<div class="room-empty">输入关键词搜索房间...</div>';
    document.getElementById('joinRoomModal').classList.add('active');
    // 后台拉取房间数据
    send({ type: 'get_rooms' });
    document.getElementById('joinRoomSearch').focus();
}

function searchRooms() {
    const query = document.getElementById('joinRoomSearch').value.trim().toLowerCase();
    if (!query) {
        document.getElementById('roomSearchList').innerHTML = '<div class="room-empty">输入关键词搜索房间...</div>';
        return;
    }
    const filtered = allRoomsCache.filter(r =>
        r.id.toLowerCase().includes(query) ||
        r.name.toLowerCase().includes(query)
    );
    renderSearchResults(filtered);
}

function renderSearchResults(rooms) {
    const el = document.getElementById('roomSearchList');
    if (!rooms.length) {
        el.innerHTML = '<div class="room-empty">没有匹配的房间</div>';
        return;
    }
    el.innerHTML = rooms.map(r => `
        <div class="room-search-item" onclick="clickRoomFromSearch('${r.id}', '${escHtml(r.name)}', ${r.has_password})">
            <div>
                <div class="room-search-name">${escHtml(r.name)} ${r.has_password ? '🔒' : ''}</div>
                <div class="room-search-meta">创建者: ${escHtml(r.creator)}</div>
            </div>
            <span class="room-search-badge">${r.id}</span>
        </div>
    `).join('');
}

function clickRoomFromSearch(roomId, roomName, hasPassword) {
    if (hasPassword) {
        promptRoomPassword(roomId, roomName);
    } else {
        joinRoomById(roomId, '');
    }
}

function joinRoomById(roomId, pass) {
    send({ type: 'join_room', room_id: roomId, password: pass || '' });
    closeModal('joinRoomModal');
    closeModal('createRoomModal');
    closeModal('roomPasswordModal');
}

// ============ 密码弹窗 ============
let pendingRoomId = '';
let pendingRoomName = '';

function promptRoomPassword(roomId, roomName) {
    pendingRoomId = roomId;
    pendingRoomName = roomName;
    document.getElementById('roomPassTargetName').textContent = roomName;
    document.getElementById('roomPassInput').value = '';
    document.getElementById('roomPassError').textContent = '';
    document.getElementById('roomPasswordModal').classList.add('active');
    document.getElementById('roomPassInput').focus();
}

function confirmRoomPassword() {
    const pass = document.getElementById('roomPassInput').value.trim();
    if (!pass) {
        document.getElementById('roomPassError').textContent = '请输入房间密码';
        return;
    }
    joinRoomById(pendingRoomId, pass);
}

// 密码弹窗回车确认
document.addEventListener('DOMContentLoaded', function() {
    const passInput = document.getElementById('roomPassInput');
    if (passInput) {
        passInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') confirmRoomPassword();
        });
    }
});

// ============ 离开房间 ============
function leaveRoom() {
    send({ type: 'leave_room' });
}

// ============ 聊天 ============
function sendMessage() {
    const input = document.getElementById('chatInput');
    const content = input.value.trim();
    if (!content) return;
    send({ type: 'send_message', room_id: currentRoom.id, content, msg_type: 'text' });
    input.value = '';
    input.style.height = 'auto';
}

function sendEmoji(emoji) {
    send({ type: 'send_message', room_id: currentRoom.id, content: emoji, msg_type: 'emoji' });
    document.getElementById('emojiPicker').classList.remove('active');
}

function onChatKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function appendMessage(msg) {
    const el = document.getElementById('chatMessages');
    const isSelf = msg.username === currentUser;
    const isEmoji = msg.msg_type === 'emoji';
    const time = new Date(msg.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const div = document.createElement('div');
    div.className = `msg-row ${isSelf ? 'self' : 'other'} ${isEmoji ? 'msg-emoji' : ''}`;
    if (isEmoji) {
        div.innerHTML = `<div class="msg-bubble">${escHtml(msg.content)}</div>`;
    } else {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(msg.username)} · ${time}</div>
                <div class="msg-bubble">${escHtml(msg.content)}</div>
            </div>`;
    }
    el.appendChild(div);
}

function appendSystem(content) {
    const el = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'msg-system';
    div.textContent = content;
    el.appendChild(div);
}

function scrollToBottom() {
    const el = document.getElementById('chatMessages');
    requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
}

function renderMembers(users) {
    const el = document.getElementById('memberList');
    el.innerHTML = (users || []).map(u => `<div class="member-item"><span class="member-dot"></span>${escHtml(u)}</div>`).join('');
}

// ============ Emoji Picker ============
function toggleEmoji() {
    const picker = document.getElementById('emojiPicker');
    if (picker.classList.contains('active')) {
        picker.classList.remove('active');
        return;
    }
    if (!picker.children.length) {
        picker.innerHTML = EMOJIS.map(e => `<span onclick="sendEmoji('${e}')">${e}</span>`).join('');
    }
    picker.classList.add('active');
}

// ============ 弹窗 ============
function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// ============ 工具 ============
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ============ 自动调整输入框高度 ============
document.getElementById('chatInput').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});

// ============ 点击弹窗外部关闭 ============
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
        if (e.target === this) this.classList.remove('active');
    });
});

// 点击页面任意位置关闭设置菜单
document.addEventListener('click', function(e) {
    const menu = document.getElementById('settingsMenu');
    const btn = document.querySelector('.btn-settings');
    if (menu && !menu.contains(e.target) && btn && !btn.contains(e.target)) {
        menu.classList.remove('active');
    }
});

// ============ 设置面板（改名 / 重置密钥） ============
function toggleSettingsMenu() {
    document.getElementById('settingsMenu').classList.toggle('active');
}

function showChangeUsernameModal() {
    document.getElementById('settingsMenu').classList.remove('active');
    document.getElementById('newUsername').value = '';
    document.getElementById('changeUserPass').value = '';
    document.getElementById('changeUsernameError').textContent = '';
    document.getElementById('changeUsernameSuccess').textContent = '';
    document.getElementById('changeUsernameModal').classList.add('active');
    document.getElementById('newUsername').focus();
}

function doChangeUsername() {
    const newName = document.getElementById('newUsername').value.trim();
    const pass = document.getElementById('changeUserPass').value.trim();
    if (!newName) { document.getElementById('changeUsernameError').textContent = '新用户名不能为空'; return; }
    if (!pass) { document.getElementById('changeUsernameError').textContent = '密钥不能为空'; return; }
    send({ type: 'change_username', new_username: newName, password: pass });
}

function showResetPasswordModal() {
    document.getElementById('settingsMenu').classList.remove('active');
    document.getElementById('oldPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('resetPasswordError').textContent = '';
    document.getElementById('resetPasswordSuccess').textContent = '';
    document.getElementById('resetPasswordModal').classList.add('active');
    document.getElementById('oldPassword').focus();
}

function doResetPassword() {
    const oldPw = document.getElementById('oldPassword').value.trim();
    const newPw = document.getElementById('newPassword').value.trim();
    if (!oldPw) { document.getElementById('resetPasswordError').textContent = '当前密钥不能为空'; return; }
    if (!newPw) { document.getElementById('resetPasswordError').textContent = '新密钥不能为空'; return; }
    send({ type: 'reset_password', old_password: oldPw, new_password: newPw });
}

// ============ 房间管理（删除） ============
function showDeleteRoomModal() {
    document.getElementById('settingsMenu').classList.remove('active');
    document.getElementById('deleteRoomError').textContent = '';
    document.getElementById('deleteRoomList').innerHTML = '<div class="room-empty">加载中...</div>';
    document.getElementById('deleteRoomModal').classList.add('active');
    send({ type: 'get_my_rooms' });
}

function renderMyRooms(rooms) {
    const el = document.getElementById('deleteRoomList');
    if (!rooms.length) {
        el.innerHTML = '<div class="room-empty">你还没有创建过房间</div>';
        return;
    }
    el.innerHTML = rooms.map(r => `
        <div class="delete-room-item">
            <div class="delete-room-info">
                <div class="delete-room-name">${escHtml(r.name)} ${r.has_password ? '🔒' : ''}</div>
                <div class="delete-room-id">ID: ${r.id}</div>
            </div>
            <button class="btn-danger" onclick="doDeleteRoom('${r.id}', '${escHtml(r.name)}')">删除</button>
        </div>
    `).join('');
}

function doDeleteRoom(roomId, roomName) {
    if (!confirm(`确定要删除房间 "${roomName}" (${roomId}) 吗？\n\n删除后不可恢复！`)) return;
    document.getElementById('deleteRoomError').textContent = '';
    send({ type: 'delete_room', room_id: roomId });
}

// ============ 文件上传 ============
function triggerFileUpload() {
    const input = document.getElementById('fileInput');
    if (input) {
        input.value = '';
        input.click();
    }
}

async function handleFileSelected(e) {
    const file = e.target.files[0];
    if (!file || !currentRoom || !currentUser) return;

    // 检查文件大小（前端预检）
    const maxSize = 4 * 1024 * 1024 * 1024; // 4GB
    if (file.size > maxSize) {
        alert('文件大小超过 4GB 限制');
        return;
    }

    // 显示保留时长选择
    const retention = await showRetentionPicker();
    if (!retention) return; // 用户取消

    // 显示上传进度
    appendSystem(`📤 正在上传: ${file.name} (${formatFileSize(file.size)}) ...`);

    try {
        const formData = new FormData();
        formData.append('file', file);

        const url = `${HTTP_URL}/api/upload?room_id=${encodeURIComponent(currentRoom.id)}&retention=${retention}&uploader=${encodeURIComponent(currentUser)}`;

        const resp = await fetch(url, {
            method: 'POST',
            body: formData,
        });

        const result = await resp.json();

        if (result.success) {
            appendSystem(`✅ 文件上传成功: ${file.name}`);
        } else {
            appendSystem(`❌ 上传失败: ${result.message}`);
        }
    } catch (err) {
        appendSystem(`❌ 上传失败: ${err.message}`);
    }
}

function showRetentionPicker() {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay active';
        overlay.innerHTML = `
            <div class="modal">
                <h3>📎 文件保留时长</h3>
                <p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:14px;">
                    选择文件在服务器上的保存时间
                </p>
                <div class="retention-options">
                    <button class="retention-btn" data-val="3h">🕐 3 小时</button>
                    <button class="retention-btn" data-val="1d">📅 1 天</button>
                    <button class="retention-btn" data-val="7d">📆 7 天</button>
                    <button class="retention-btn" data-val="30d">🗓 30 天</button>
                    <button class="retention-btn" data-val="forever">♾️ 永久</button>
                </div>
                <div class="modal-btns" style="margin-top:14px;">
                    <button class="btn btn-outline cancel-retention">取消</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelectorAll('.retention-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.body.removeChild(overlay);
                resolve(btn.dataset.val);
            });
        });
        overlay.querySelector('.cancel-retention').addEventListener('click', () => {
            document.body.removeChild(overlay);
            resolve(null);
        });
        overlay.addEventListener('click', function(e) {
            if (e.target === this) {
                document.body.removeChild(overlay);
                resolve(null);
            }
        });
    });
}

function appendFileMessage(file) {
    const el = document.getElementById('chatMessages');
    const isSelf = file.uploaded_by === currentUser;
    const time = new Date(file.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const retentionLabel = {
        '3h': '3小时', '1d': '1天', '7d': '7天', '30d': '30天', 'forever': '永久'
    }[file.retention] || file.retention;

    const div = document.createElement('div');
    div.className = `msg-row ${isSelf ? 'self' : 'other'} file-msg`;
    div.setAttribute('data-file-id', file.id);
    div.innerHTML = `
        <div>
            <div class="msg-user">${escHtml(file.uploaded_by)} · ${time}</div>
            <div class="msg-bubble file-bubble">
                <div class="file-icon">📄</div>
                <div class="file-info">
                    <div class="file-name" title="${escHtml(file.filename)}">${escHtml(file.filename)}</div>
                    <div class="file-meta">${formatFileSize(file.file_size)} · 保留 ${retentionLabel}</div>
                </div>
                <a class="file-download" href="${HTTP_URL}/api/files/${file.id}" download title="下载">
                    ⬇️
                </a>
            </div>
        </div>`;
    el.appendChild(div);
}

function renderFileList() {
    const el = document.getElementById('fileListContent');
    if (!el) return;
    if (!roomFiles.length) {
        el.innerHTML = '<div class="file-empty">暂无共享文件</div>';
        return;
    }
    const retentionLabel = {
        '3h': '3小时', '1d': '1天', '7d': '7天', '30d': '30天', 'forever': '永久'
    };
    el.innerHTML = roomFiles.map(f => `
        <div class="file-item" data-file-id="${f.id}">
            <div class="file-item-icon">📄</div>
            <div class="file-item-info">
                <div class="file-item-name" title="${escHtml(f.filename)}">${escHtml(f.filename)}</div>
                <div class="file-item-meta">${formatFileSize(f.file_size)} · ${retentionLabel[f.retention] || f.retention}</div>
            </div>
            <div class="file-item-actions">
                <a class="file-item-dl" href="${HTTP_URL}/api/files/${f.id}" download title="下载">⬇️</a>
                ${f.uploaded_by === currentUser ? `<button class="file-item-del" onclick="deleteFile('${f.id}')" title="删除">🗑</button>` : ''}
            </div>
        </div>
    `).join('');
}

function deleteFile(fileId) {
    if (!confirm('确定要删除这个文件吗？')) return;
    send({ type: 'delete_file', file_id: fileId });
}

function toggleFilePanel() {
    const panel = document.getElementById('filePanel');
    if (panel) {
        panel.classList.toggle('active');
        if (panel.classList.contains('active')) {
            send({ type: 'get_files' });
        }
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const size = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
    return `${size} ${units[i]}`;
}

// ============ 启动 ============
connectWS();
showView('login');
