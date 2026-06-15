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
        case 'file_list':
            roomFiles = msg.files || [];
            renderFileList();
            break;
        case 'new_file':
            appendFileMessage(msg.file);
            scrollToBottom();
            if (currentRoom) send({ type: 'get_files' });
            break;
        case 'file_deleted':
            roomFiles = roomFiles.filter(f => f.id !== msg.file_id);
            renderFileList();
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
                send({ type: 'get_my_rooms' });
                refreshRooms();
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

// ============ 事件绑定 ============
// 点击弹窗外部关闭
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

// ============ 启动 ============
connectWS();
showView('login');
