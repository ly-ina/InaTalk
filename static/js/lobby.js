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

// ============ 加入房间（搜索） ============
let allRoomsCache = [];

function showJoinRoomModal() {
    document.getElementById('joinRoomSearch').value = '';
    document.getElementById('joinRoomError').textContent = '';
    document.getElementById('roomSearchList').innerHTML = '<div class="room-empty">输入关键词搜索房间...</div>';
    document.getElementById('joinRoomModal').classList.add('active');
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

// ============ 房间管理 ============
function showRoomManageModal() {
    document.getElementById('settingsMenu').classList.remove('active');
    document.getElementById('manageRoomError').textContent = '';
    document.getElementById('manageRoomList').innerHTML = '<div class="room-empty">加载中...</div>';
    document.getElementById('roomManageModal').classList.add('active');
    send({ type: 'get_my_rooms' });
}

function renderMyRooms(rooms) {
    const el = document.getElementById('manageRoomList');
    if (!rooms.length) {
        el.innerHTML = '<div class="room-empty">你还没有创建过房间</div>';
        return;
    }
    el.innerHTML = rooms.map(r => `
        <div class="manage-room-item">
            <div class="manage-room-info">
                <div class="manage-room-name">${escHtml(r.name)} ${r.has_password ? '🔒' : ''} ${r.background ? '🖼️' : ''}</div>
                <div class="manage-room-id">ID: ${r.id}</div>
            </div>
            <div class="manage-room-actions">
                <button class="btn-manage btn-key" onclick="showPasswordManage('${r.id}', '${escHtml(r.name)}', ${r.has_password})" title="密码管理">🔑</button>
                <button class="btn-manage btn-bg" onclick="showBackgroundManage('${r.id}', '${escHtml(r.name)}', '${(r.background || '').replace(/'/g, "\\'")}')" title="背景管理">🖼️</button>
                <button class="btn-manage btn-del" onclick="doDeleteRoom('${r.id}', '${escHtml(r.name)}')" title="删除房间">🗑️</button>
            </div>
        </div>
    `).join('');
}

function doDeleteRoom(roomId, roomName) {
    if (!confirm(`确定要删除房间 "${roomName}" (${roomId}) 吗？\n\n删除后不可恢复！所有消息和文件将被永久移除。`)) return;
    document.getElementById('manageRoomError').textContent = '';
    send({ type: 'delete_room', room_id: roomId });
}

// ============ 房间密码管理 ============
let currentPasswordRoomId = '';
let currentPasswordRoomName = '';
let currentPasswordRoomHasPw = false;

function showPasswordManage(roomId, roomName, hasPassword) {
    currentPasswordRoomId = roomId;
    currentPasswordRoomName = roomName;
    currentPasswordRoomHasPw = hasPassword;

    const title = document.getElementById('roomPasswordManageTitle');
    const info = document.getElementById('roomPasswordManageInfo');
    const oldGroup = document.getElementById('oldRoomPasswordGroup');
    const newGroup = document.getElementById('newRoomPasswordGroup');
    const actionBtn = document.getElementById('roomPasswordActionBtn');
    const errEl = document.getElementById('roomPasswordManageError');

    errEl.textContent = '';
    document.getElementById('oldRoomPassword').value = '';
    document.getElementById('newRoomPassword').value = '';

    if (hasPassword) {
        title.textContent = '🔑 管理房间密码';
        info.textContent = `房间 "${roomName}" 当前有密码保护`;
        oldGroup.style.display = 'block';
        newGroup.style.display = 'block';
        actionBtn.textContent = '修改密码';
        actionBtn.onclick = function() { doRoomPasswordAction('change'); };

        // 添加移除密码按钮
        if (!document.getElementById('removePasswordBtn')) {
            const removeBtn = document.createElement('button');
            removeBtn.id = 'removePasswordBtn';
            removeBtn.className = 'btn btn-outline';
            removeBtn.style.marginTop = '6px';
            removeBtn.textContent = '移除密码';
            removeBtn.onclick = function() { doRoomPasswordAction('remove'); };
            actionBtn.parentElement.appendChild(removeBtn);
        }
        const removeBtn = document.getElementById('removePasswordBtn');
        if (removeBtn) removeBtn.style.display = 'block';
    } else {
        title.textContent = '🔑 设置房间密码';
        info.textContent = `房间 "${roomName}" 当前无密码`;
        oldGroup.style.display = 'none';
        newGroup.style.display = 'block';
        actionBtn.textContent = '设置密码';
        actionBtn.onclick = function() { doRoomPasswordAction('set'); };
        const removeBtn = document.getElementById('removePasswordBtn');
        if (removeBtn) removeBtn.style.display = 'none';
    }

    document.getElementById('roomPasswordManageModal').classList.add('active');
    document.getElementById('newRoomPassword').focus();
}

function doRoomPasswordAction(action) {
    const errEl = document.getElementById('roomPasswordManageError');
    errEl.textContent = '';

    const oldPw = document.getElementById('oldRoomPassword').value.trim();
    const newPw = document.getElementById('newRoomPassword').value.trim();

    if (action === 'remove') {
        if (!oldPw) { errEl.textContent = '请输入当前房间密码'; return; }
        if (!confirm(`确定要移除房间 "${currentPasswordRoomName}" 的密码吗？`)) return;
        send({ type: 'remove_room_password', room_id: currentPasswordRoomId, old_password: oldPw });
    } else if (action === 'set') {
        if (!newPw) { errEl.textContent = '请输入新密码'; return; }
        send({ type: 'change_room_password', room_id: currentPasswordRoomId, old_password: '', new_password: newPw });
    } else if (action === 'change') {
        if (!oldPw) { errEl.textContent = '请输入当前房间密码'; return; }
        if (!newPw) { errEl.textContent = '请输入新密码'; return; }
        send({ type: 'change_room_password', room_id: currentPasswordRoomId, old_password: oldPw, new_password: newPw });
    }
}

// ============ 房间背景管理 ============
let currentBackgroundRoomId = '';
let currentBackgroundRoomName = '';

function showBackgroundManage(roomId, roomName, background) {
    currentBackgroundRoomId = roomId;
    currentBackgroundRoomName = roomName;

    const info = document.getElementById('roomBackgroundInfo');
    const preview = document.getElementById('roomBackgroundPreview');
    const img = document.getElementById('roomBackgroundImg');
    const fileInput = document.getElementById('backgroundFileInput');
    const errEl = document.getElementById('roomBackgroundError');
    const successEl = document.getElementById('roomBackgroundSuccess');

    errEl.textContent = '';
    successEl.textContent = '';
    fileInput.value = '';

    if (background) {
        info.textContent = `房间 "${roomName}" 当前有背景`;
        preview.style.display = 'block';
        img.src = background;
    } else {
        info.textContent = `房间 "${roomName}" 当前无背景`;
        preview.style.display = 'none';
    }

    document.getElementById('roomBackgroundModal').classList.add('active');
}

function doUploadBackground() {
    const fileInput = document.getElementById('backgroundFileInput');
    const errEl = document.getElementById('roomBackgroundError');
    const successEl = document.getElementById('roomBackgroundSuccess');
    errEl.textContent = '';
    successEl.textContent = '';

    const file = fileInput.files[0];
    if (!file) {
        errEl.textContent = '请选择图片文件';
        return;
    }

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'];
    if (!allowedTypes.includes(file.type)) {
        errEl.textContent = '不支持的图片格式，支持: jpg, png, gif, webp, bmp';
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        errEl.textContent = '背景图片不能超过 10MB';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${HTTP_URL}/api/upload_background?room_id=${encodeURIComponent(currentBackgroundRoomId)}&username=${encodeURIComponent(currentUser || '')}`);
    xhr.onload = function() {
        try {
            const result = JSON.parse(xhr.responseText);
            if (result.success) {
                successEl.textContent = result.message || '背景上传成功';
                setTimeout(() => {
                    closeModal('roomBackgroundModal');
                    send({ type: 'get_my_rooms' });
                }, 1500);
            } else {
                errEl.textContent = result.message || '上传失败';
            }
        } catch (e) {
            errEl.textContent = '上传响应解析失败';
        }
    };
    xhr.onerror = function() {
        errEl.textContent = '上传请求失败，请检查网络';
    };
    xhr.send(formData);
}
