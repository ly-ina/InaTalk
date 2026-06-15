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

// ============ 删除房间 ============
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
