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

// ============ 输入框自动高度 ============
document.getElementById('chatInput').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});
