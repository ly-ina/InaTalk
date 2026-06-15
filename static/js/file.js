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

// ============ 文件消息 ============
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
                <a class="file-download" href="${HTTP_URL}/api/files/${file.id}" download title="下载">⬇️</a>
            </div>
        </div>`;
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
