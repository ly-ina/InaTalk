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
    // 公私聊兼容：私聊时发 private_message，群聊时发 send_message
    if (typeof privateTarget !== 'undefined' && privateTarget) {
        send({ type: 'send_private_message', content: emoji, msg_type: 'emoji' });
    } else if (currentRoom) {
        send({ type: 'send_message', room_id: currentRoom.id, content: emoji, msg_type: 'emoji' });
    }
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
    const isSticker = msg.msg_type === 'sticker';
    const time = new Date(msg.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const div = document.createElement('div');
    div.className = `msg-row ${isSelf ? 'self' : 'other'} ${isEmoji ? 'msg-emoji' : ''} ${isSticker ? 'sticker-msg' : ''}`;
    if (isSticker) {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(msg.username)} · ${time}</div>
                <img class="chat-img" src="${escHtml(msg.content)}" alt="" loading="lazy"
                     onclick="openLightbox('${escHtml(msg.content)}')" title="左键放大 | 右键下载" />
            </div>`;
    } else if (isEmoji) {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(msg.username)} · ${time}</div>
                <div class="msg-bubble">${escHtml(msg.content)}</div>
            </div>`;
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
    el.innerHTML = (users || []).map(u => {
        const isSelf = u === currentUser;
        return `<div class="member-item${isSelf ? '' : ' clickable'}"${isSelf ? '' : ` onclick="openPrivateChat('${escHtml(u)}')"`}>
            <span class="member-dot"></span>${escHtml(u)}
        </div>`;
    }).join('');
}

// ============ Emoji Picker ============
function toggleEmoji() {
    const picker = document.getElementById('emojiPicker');
    document.getElementById('stickerPicker').classList.remove('active');
    if (picker.classList.contains('active')) {
        picker.classList.remove('active');
        return;
    }
    if (!picker.children.length) {
        picker.innerHTML = EMOJIS.map(e => `<span onclick="sendEmoji('${e}')">${e}</span>`).join('');
    }
    picker.classList.add('active');
}

// ============ 表情包面板 ============
function toggleStickers() {
    const picker = document.getElementById('stickerPicker');
    document.getElementById('emojiPicker').classList.remove('active');
    if (picker.classList.contains('active')) {
        picker.classList.remove('active');
        return;
    }
    picker.classList.add('active');
    renderStickers();
}

function closeStickerPanel() {
    document.getElementById('stickerPicker').classList.remove('active');
}

// ============ 输入框自动高度 ============
document.getElementById('chatInput').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});

// ============ 房间公告 ============
let announcementDismissed = false;    // 是否已折叠
let _cachedAnnouncement = null;      // 折叠时保留原文

function renderAnnouncement(announcement) {
    const bar = document.getElementById('roomAnnouncement');
    const text = document.getElementById('announcementText');
    const editBtn = document.getElementById('announcementEditBtn');
    const closeBtn = document.getElementById('announcementCloseBtn');
    const isCreator = currentRoom && currentUser === currentRoom.creator;
    announcementDismissed = false;
    _cachedAnnouncement = announcement || null;

    bar.classList.remove('announcement-collapsed');
    bar.onclick = null;  // 清除折叠态点击事件

    if (announcement) {
        // 有公告：所有人可见（展开态）
        text.textContent = announcement;
        text.style.color = '#1e40af';
        bar.style.display = 'flex';
        closeBtn.style.display = 'flex';
        editBtn.style.display = isCreator ? 'inline-flex' : 'none';
    } else if (isCreator) {
        text.textContent = '暂无公告，点击右侧按钮设置';
        text.style.color = '#94a3b8';
        bar.style.display = 'flex';
        closeBtn.style.display = 'flex';           // 允许关闭空公告栏
        editBtn.style.display = 'inline-flex';
    } else {
        bar.style.display = 'none';
        text.textContent = '';
        closeBtn.style.display = 'none';
        editBtn.style.display = 'none';
    }
}

function dismissAnnouncement() {
    announcementDismissed = true;
    const bar = document.getElementById('roomAnnouncement');
    const text = document.getElementById('announcementText');
    const closeBtn = document.getElementById('announcementCloseBtn');
    const editBtn = document.getElementById('announcementEditBtn');

    // 折叠提示文案：有公告 vs 无公告
    text.textContent = _cachedAnnouncement ? '📢 公告 · 点击展开 ▼' : '📢 暂无公告 · 点击展开 ▼';
    text.style.color = '#64748b';
    closeBtn.style.display = 'none';
    editBtn.style.display = 'none';
    bar.style.display = 'flex';
    bar.classList.add('announcement-collapsed');

    bar.onclick = function(e) {
        if (e.target === closeBtn || e.target === editBtn) return;
        expandAnnouncement();
    };
}

function expandAnnouncement() {
    announcementDismissed = false;
    const bar = document.getElementById('roomAnnouncement');
    const text = document.getElementById('announcementText');
    const closeBtn = document.getElementById('announcementCloseBtn');
    const editBtn = document.getElementById('announcementEditBtn');
    const isCreator = currentRoom && currentUser === currentRoom.creator;

    bar.classList.remove('announcement-collapsed');
    bar.onclick = null;

    if (_cachedAnnouncement) {
        // 恢复完整公告
        text.textContent = _cachedAnnouncement;
        text.style.color = '#1e40af';
    } else {
        // 恢复空占位
        text.textContent = '暂无公告，点击右侧按钮设置';
        text.style.color = '#94a3b8';
    }
    closeBtn.style.display = 'flex';
    editBtn.style.display = isCreator ? 'inline-flex' : 'none';
}

// 私聊滚动
function scrollPrivateChat() {
    const el = document.getElementById('privateChatMessages');
    requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
}

function showAnnouncementEditor() {
    if (!currentRoom || currentUser !== currentRoom.creator) return;
    const input = document.getElementById('announcementInput');
    const charCount = document.getElementById('announcementCharCount');
    const currentText = document.getElementById('announcementText').textContent || '';
    input.value = currentText;
    charCount.textContent = currentText.length + '/500';
    document.getElementById('announcementError').textContent = '';
    document.getElementById('announcementSuccess').textContent = '';
    document.getElementById('clearAnnouncementBtn').style.display = currentText ? 'inline-block' : 'none';
    document.getElementById('announcementModal').classList.add('active');
}

function doSetAnnouncement() {
    const content = document.getElementById('announcementInput').value.trim();
    if (!content) {
        document.getElementById('announcementError').textContent = '公告内容不能为空';
        return;
    }
    send({ type: 'set_announcement', room_id: currentRoom.id, content });
}

function doClearAnnouncement() {
    send({ type: 'set_announcement', room_id: currentRoom.id, content: null });
}

// 公告输入框字数统计
document.getElementById('announcementInput').addEventListener('input', function() {
    document.getElementById('announcementCharCount').textContent = this.value.length + '/500';
    document.getElementById('clearAnnouncementBtn').style.display = this.value.length > 0 ? 'inline-block' : 'none';
});
