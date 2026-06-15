// ============ 工具函数 ============
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const size = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
    return `${size} ${units[i]}`;
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

function toggleSettingsMenu() {
    document.getElementById('settingsMenu').classList.toggle('active');
}
