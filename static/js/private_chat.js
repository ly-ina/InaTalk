// ============ 私聊 ============
let privateTarget = null;
let privateChatId = null;

let _prevView = null;  // 进入私聊前所在视图

function openPrivateChat(target) {
    if (!currentUser || target === currentUser) return;
    privateTarget = target;
    document.getElementById('privateTargetName').textContent = '与 ' + escHtml(target) + ' 私聊';
    document.getElementById('privateChatMessages').innerHTML = '';

    // 记住当前视图，关闭时返回
    _prevView = currentRoom ? 'chat' : 'lobby';

    showView('privateChat');
    document.getElementById('privateChatInput').focus();
    send({ type: 'start_private_chat', target });
}

function closePrivateChat() {
    privateTarget = null;
    privateChatId = null;
    document.getElementById('privateChatMessages').innerHTML = '';

    // 返回之前的视图
    if (_prevView === 'chat' && currentRoom) {
        showView('chat');
    } else {
        showView('lobby');
        refreshRooms();
    }

    if (currentUser) {
        send({ type: 'close_private_chat' });
    }
}

// 私聊独立的表情/表情包面板（简单实现）
function togglePrivateEmoji() {
    if (typeof toggleEmoji === 'function') {
        toggleEmoji();
    }
}

function togglePrivateStickers() {
    if (typeof toggleStickers === 'function') {
        toggleStickers();
    }
}

function toggleRoomChatUI(show) {
    const d = show ? '' : 'none';
    const chatMsgs = document.getElementById('chatMessages');
    const inputArea = document.querySelector('.chat-input-area');
    const roomAnnounce = document.getElementById('roomAnnouncement');
    const filePanel = document.getElementById('filePanel');

    if (chatMsgs) chatMsgs.style.display = d;
    if (inputArea) inputArea.style.display = d;
    if (filePanel) filePanel.style.display = d;
    // 公告：私聊时永远隐藏
    if (!show) {
        if (roomAnnounce) roomAnnounce.style.display = 'none';
    } else {
        if (roomAnnounce && !announcementDismissed && _cachedAnnouncement) {
            roomAnnounce.style.display = 'flex';
        } else if (roomAnnounce && announcementDismissed) {
            roomAnnounce.style.display = 'flex';
        }
    }
    // 表情/表情包面板不隐藏，公私聊共享
}

function appendPrivateMessage(msg) {
    const el = document.getElementById('privateChatMessages');
    const isSelf = msg.sender === currentUser;
    const time = new Date(msg.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const div = document.createElement('div');
    div.className = `msg-row ${isSelf ? 'self' : 'other'}`;
    div.innerHTML = `
        <div>
            <div class="msg-user">${escHtml(msg.sender)} · ${time}</div>
            <div class="msg-bubble">${escHtml(msg.content)}</div>
        </div>`;
    el.appendChild(div);
}

function sendPrivateMessage() {
    const input = document.getElementById('privateChatInput');
    const content = input.value.trim();
    if (!content || !privateTarget) return;
    send({ type: 'send_private_message', content, msg_type: 'text' });
    input.value = '';
    input.style.height = 'auto';
}

function onPrivateChatKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendPrivateMessage();
    }
}

// ============ 私聊文件上传 ============
function triggerPrivateFileUpload() {
    document.getElementById('privateFileInput').click();
}

function handlePrivateFileSelected(event) {
    const file = event.target.files[0];
    if (!file || !privateTarget) return;
    if (file.size > 50 * 1024 * 1024) {
        alert('文件不能超过 50MB');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${HTTP_URL}/api/private_upload?target=${encodeURIComponent(privateTarget)}&uploader=${encodeURIComponent(currentUser)}`);
    xhr.onload = function() {
        try {
            const result = JSON.parse(xhr.responseText);
            if (result.success) {
                // 私聊文件消息：内容是 JSON 串，前端渲染时解析
                const fileInfo = {
                    url: result.url,
                    filename: result.filename,
                    file_size: result.file_size,
                    file_type: result.file_type || 'application/octet-stream',
                    created_at: result.created_at
                };
                send({ type: 'send_private_message', content: JSON.stringify(fileInfo), msg_type: 'file' });
            } else {
                alert(result.message || '上传失败');
            }
        } catch (e) {
            alert('上传响应解析失败');
        }
    };
    xhr.onerror = function() { alert('上传请求失败'); };
    xhr.send(formData);
    event.target.value = '';
}

// 私聊消息渲染：支持 sticker + 文件类型
const origAppendPrivateMsg = appendPrivateMessage;
appendPrivateMessage = function(msg) {
    const el = document.getElementById('privateChatMessages');
    const isSelf = msg.sender === currentUser;
    const time = new Date(msg.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

    // 表情包
    if (msg.msg_type === 'sticker') {
        const div = document.createElement('div');
        div.className = `msg-row ${isSelf ? 'self' : 'other'} sticker-msg`;
        div.innerHTML = `<div>
            <div class="msg-user">${escHtml(msg.sender)} · ${time}</div>
            <img class="chat-img" src="${escHtml(msg.content)}" alt="" loading="lazy"
                 onclick="openLightbox('${escHtml(msg.content)}')" title="左键放大 | 右键下载" />
        </div>`;
        el.appendChild(div);
        return;
    }

    if (msg.msg_type === 'file') {
        try {
            const fi = JSON.parse(msg.content);
            const div = document.createElement('div');
            div.className = `msg-row ${isSelf ? 'self' : 'other'}`;
            const isImage = /^image\/(jpeg|png|gif|webp|jpg)/.test(fi.file_type || '');
            const isVideo = /^video\//.test(fi.file_type || '');
            if (isImage) {
                div.innerHTML = `<div><div class="msg-user">${escHtml(msg.sender)} · ${time}</div>
                    <img class="chat-img" src="${fi.url}" alt="" loading="lazy" onclick="openLightbox('${fi.url}')" title="左键放大 | 右键下载" /></div>`;
            } else if (isVideo) {
                div.innerHTML = `<div><div class="msg-user">${escHtml(msg.sender)} · ${time}</div>
                    <video class="chat-img" controls src="${fi.url}" style="max-width:300px;max-height:200px;"></video></div>`;
            } else {
                const sizeStr = fi.file_size ? (fi.file_size > 1024*1024 ? (fi.file_size/(1024*1024)).toFixed(1)+'MB' : (fi.file_size/1024).toFixed(1)+'KB') : '';
                div.innerHTML = `<div><div class="msg-user">${escHtml(msg.sender)} · ${time}</div>
                    <div class="msg-bubble">📎 <a href="${fi.url}" target="_blank" style="color:inherit;" download>${escHtml(fi.filename || '文件')}</a> ${sizeStr}</div></div>`;
            }
            el.appendChild(div);
            return;
        } catch (e) { /* fall through to text */ }
    }

    // 默认文本/表情渲染
    origAppendPrivateMsg(msg);
};

// 私聊输入框自动高度
document.getElementById('privateChatInput').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 80) + 'px';
});
