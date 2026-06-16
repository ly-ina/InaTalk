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

    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
        alert('文件大小超过 4GB 限制');
        return;
    }

    const retention = await showRetentionPicker();
    if (!retention) return;

    appendSystem(`📤 正在上传: ${file.name} (${formatFileSize(file.size)}) ...`);

    try {
        const formData = new FormData();
        formData.append('file', file);

        const url = `${HTTP_URL}/api/upload?room_id=${encodeURIComponent(currentRoom.id)}&retention=${retention}&uploader=${encodeURIComponent(currentUser)}`;

        const resp = await fetch(url, { method: 'POST', body: formData });
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

// ============ 文件类型判断 ============
function getMediaType(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    const images = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'];
    const videos = ['mp4', 'webm', 'mov', 'avi', 'mkv'];
    if (images.includes(ext)) return 'image';
    if (videos.includes(ext)) return 'video';
    return 'file';
}

// ============ 文件消息 ============
function appendFileMessage(file) {
    const el = document.getElementById('chatMessages');
    const isSelf = file.uploaded_by === currentUser;
    const time = new Date(file.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const retentionLabel = {
        '3h': '3小时', '1d': '1天', '7d': '7天', '30d': '30天', 'forever': '永久'
    }[file.retention] || file.retention;
    const viewUrl = `${HTTP_URL}/api/files/${file.id}/view`;

    const div = document.createElement('div');
    div.className = `msg-row ${isSelf ? 'self' : 'other'} file-msg`;
    div.setAttribute('data-file-id', file.id);

    const mediaType = getMediaType(file.filename);
    if (mediaType === 'image') {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(file.uploaded_by)} · ${time}</div>
                <img class="chat-img" src="${viewUrl}" alt="" loading="lazy"
                     onclick="openLightbox('${viewUrl}')" title="左键放大 | 右键下载" />
            </div>`;
    } else if (mediaType === 'video') {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(file.uploaded_by)} · ${time}</div>
                <div class="msg-bubble media-bubble">
                    <video class="chat-media" src="${viewUrl}" controls preload="metadata"
                           title="${escHtml(file.filename)}"></video>
                    <div class="media-caption">${escHtml(file.filename)} · ${formatFileSize(file.file_size)}</div>
                </div>
            </div>`;
    } else {
        div.innerHTML = `
            <div>
                <div class="msg-user">${escHtml(file.uploaded_by)} · ${time}</div>
                <div class="msg-bubble file-bubble">
                    <div class="file-icon">📄</div>
                    <div class="file-info">
                        <div class="file-name" title="${escHtml(file.filename)}">${escHtml(file.filename)}</div>
                        <div class="file-meta">${formatFileSize(file.file_size)} · 保留 ${retentionLabel}</div>
                    </div>
                    <a class="file-download" href="${HTTP_URL}/api/files/${file.id}" download title="下载">⬇️</a>
                </div>
            </div>`;
    }
    el.appendChild(div);
}

// ============ 文件面板 ============
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
    el.innerHTML = roomFiles
        .filter(f => getMediaType(f.filename) !== 'image')
        .map(f => {
        const viewUrl = `${HTTP_URL}/api/files/${f.id}/view`;
        const mt = getMediaType(f.filename);
        let icon = '📄';
        if (mt === 'video') icon = '🎬';
        return `
            <div class="file-item" data-file-id="${f.id}">
                <div class="file-item-icon">${icon}</div>
                <div class="file-item-info">
                    <div class="file-item-name" title="${escHtml(f.filename)}">${escHtml(f.filename)}</div>
                    <div class="file-item-meta">${formatFileSize(f.file_size)} · ${retentionLabel[f.retention] || f.retention}</div>
                </div>
                <div class="file-item-actions">
                    ${mt === 'video' ? `<a class="file-item-dl" href="${viewUrl}" target="_blank" title="预览">👁️</a>` : ''}
                    <a class="file-item-dl" href="${HTTP_URL}/api/files/${f.id}" download title="下载">⬇️</a>
                    ${f.uploaded_by === currentUser ? `<button class="file-item-del" onclick="deleteFile('${f.id}')" title="删除">🗑</button>` : ''}
            </div>
        </div>
    `}).join('');
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

// ============ 图片灯箱（左键放大）============
function openLightbox(url) {
    let box = document.getElementById('img-lightbox');
    if (!box) {
        box = document.createElement('div');
        box.id = 'img-lightbox';
        box.className = 'lightbox';
        box.innerHTML = `
            <div class="lightbox-bg"></div>
            <img class="lightbox-img" src="" alt="" />
            <button class="lightbox-close" title="关闭">✕</button>
            <a class="lightbox-dl" href="" download title="下载图片">⬇️</a>`;
        document.body.appendChild(box);

        const close = () => box.classList.remove('active');
        box.querySelector('.lightbox-bg').addEventListener('click', close);
        box.querySelector('.lightbox-close').addEventListener('click', close);
        box.addEventListener('click', function(e) {
            if (e.target === box) close();
        });
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') close();
        });
    }
    box.querySelector('.lightbox-img').src = url;
    box.querySelector('.lightbox-dl').href = url.replace('/view', '');
    box.classList.add('active');
}

// ============ 表情包（Supabase stickers 表）============
let stickerCache = [];  // { id, storage_key, filename }

async function loadStickers() {
    if (!currentRoom) return;
    try {
        const resp = await fetch(`${HTTP_URL}/api/stickers/${encodeURIComponent(currentRoom.id)}`);
        const data = await resp.json();
        stickerCache = data.stickers || [];
    } catch {
        stickerCache = [];
    }
}

function toggleStickerPanel() {
    toggleStickers();
}

async function renderStickers() {
    if (!currentRoom) return;
    await loadStickers();
    const grid = document.getElementById('stickerGrid');
    if (!grid) return;
    const myStickers = stickerCache.filter(s => s.uploaded_by === currentUser);
    if (!myStickers.length) {
        grid.innerHTML = '<div class="file-empty">暂无表情包，上传一张吧</div>';
        return;
    }
    grid.innerHTML = myStickers.map(s => {
        const viewUrl = `${HTTP_URL}/api/stickers/view/${s.id}`;
        return `
            <div class="sticker-item"
                 onclick="sendSticker('${s.id}')"
                 oncontextmenu="showCtxMenu(event, '${HTTP_URL}/api/stickers/view/${s.id}')">
                <img src="${viewUrl}" alt="" loading="lazy" />
                <button class="sticker-del" onclick="event.stopPropagation();delSticker('${s.id}')" title="删除">✕</button>
            </div>`;
    }).join('');
}

async function delSticker(stickerId) {
    await fetch(`${HTTP_URL}/api/stickers/${stickerId}`, { method: 'DELETE' });
    renderStickers();
}

function sendSticker(stickerId) {
    const viewUrl = `${HTTP_URL}/api/stickers/view/${stickerId}`;
    send({ type: 'send_message', room_id: currentRoom.id, content: viewUrl, msg_type: 'sticker' });
    closeStickerPanel();
}

function triggerStickerUpload() {
    document.getElementById('stickerInput').click();
}

async function handleStickerUpload(e) {
    const file = e.target.files[0];
    if (!file || !currentRoom || !currentUser) return;
    if (!file.type.startsWith('image/')) { alert('只支持图片'); return; }
    const formData = new FormData();
    formData.append('file', file);
    const url = `${HTTP_URL}/api/stickers?room_id=${encodeURIComponent(currentRoom.id)}&uploader=${encodeURIComponent(currentUser)}`;
    try {
        const resp = await fetch(url, { method: 'POST', body: formData });
        const result = await resp.json();
        if (result.success) {
            renderStickers();
        } else {
            alert('上传失败: ' + (result.message || ''));
        }
    } catch (err) {
        alert('上传失败: ' + err.message);
    }
    e.target.value = '';
}

// ============ 自定义右键菜单 ============
function showCtxMenu(e, downloadUrl) {
    e.preventDefault();
    ctxTargetUrl = downloadUrl;
    const menu = document.getElementById('ctxMenu');
    menu.style.display = 'block';
    menu.style.left = e.pageX + 'px';
    menu.style.top = e.pageY + 'px';
}

function ctxDownload() {
    if (ctxTargetUrl) {
        const a = document.createElement('a');
        a.href = ctxTargetUrl;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
    document.getElementById('ctxMenu').style.display = 'none';
}

document.addEventListener('click', function() {
    document.getElementById('ctxMenu').style.display = 'none';
});
