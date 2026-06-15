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
    localStorage.setItem('im_user', user);
    localStorage.setItem('im_pass', pass);
    connectWS();
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
    localStorage.removeItem('im_user');
    localStorage.removeItem('im_pass');
    currentUser = null;
    currentRoom = null;
    showView('login');
    document.getElementById('loginBtn').disabled = false;
    document.getElementById('loginBtn').textContent = '登 录';
    document.getElementById('loginUser').value = '';
    document.getElementById('loginPass').value = '';
}

// ============ 修改用户名 ============
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

// ============ 重置密钥 ============
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
