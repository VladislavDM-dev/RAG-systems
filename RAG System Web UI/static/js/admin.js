// === Админ-панель: статус, конфигурация, папки, пользователи, шаблон ===
const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';

let adminSyncTimer = null;
let adminSyncActive = false;

async function loadAdminInfo() {
    try {
        const res = await apiFetch('/api/admin/info');
        const data = await res.json();
        document.getElementById('adm-version').textContent = data.version || '—';
        document.getElementById('adm-doc-count').textContent = data.document_count ?? 0;
        document.getElementById('adm-index-updated').textContent = data.index_updated || '—';
        const backEl = document.getElementById('adm-backend-status');
        if (data.status_backend) {
            backEl.innerHTML = '<span class="badge bg-success">OK</span> ' + (data.provider || '');
        } else {
            backEl.innerHTML = '<span class="badge bg-danger">Ошибка</span>';
        }

        const banner = document.getElementById('backend-status');
        if (data.is_syncing) {
            banner.className = 'alert alert-primary mb-0';
            banner.innerHTML = '<i class="bi bi-arrow-repeat sync-spin me-2"></i>Идёт синхронизация: ' + (data.status || '');
            adminSyncActive = true;
        } else {
            banner.className = data.status_backend ? 'alert alert-success mb-0' : 'alert alert-danger mb-0';
            banner.innerHTML = data.status_backend
                ? '<i class="bi bi-check-circle me-2"></i>Система готова к работе'
                : '<i class="bi bi-x-circle me-2"></i>Бэкенд недоступен';
            adminSyncActive = false;
        }
    } catch (e) {
        const banner = document.getElementById('backend-status');
        banner.className = 'alert alert-danger mb-0';
        banner.innerHTML = '<i class="bi bi-x-circle me-2"></i>Не удалось получить статус: ' + e.message;
    }
}

async function loadFolders() {
    try {
        const res = await apiFetch('/api/admin/folders');
        const data = await res.json();
        const list = document.getElementById('folders-list');
        list.innerHTML = '';
        (data.folders || []).forEach(folder => {
            const item = document.createElement('div');
            item.className = 'folder-item';
            item.innerHTML = '<span class="folder-path">' + escapeHtml(folder) + '</span>' +
                '<button class="btn btn-sm btn-link text-danger p-0 folder-del" data-folder="' + escapeHtml(folder) + '"><i class="bi bi-x-lg"></i></button>';
            item.querySelector('.folder-del').addEventListener('click', () => removeFolder(folder));
            list.appendChild(item);
        });
    } catch (e) {
        console.error('Ошибка загрузки папок:', e);
    }
}

async function setFolders(folders) {
    try {
        await apiFetch('/api/admin/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folders }),
        });
        loadFolders();
    } catch (e) {
        console.error('Ошибка сохранения папок:', e);
    }
}

function addFolder() {
    const input = document.getElementById('folder-input');
    const path = input.value.trim();
    if (!path) return;
    apiFetch('/api/admin/folders').then(r => r.json()).then(data => {
        const folders = data.folders || [];
        if (!folders.includes(path)) folders.push(path);
        setFolders(folders);
        input.value = '';
    });
}

function removeFolder(path) {
    apiFetch('/api/admin/folders').then(r => r.json()).then(data => {
        const folders = (data.folders || []).filter(f => f !== path);
        setFolders(folders);
    });
}

async function loadUsers() {
    try {
        const res = await apiFetch('/api/admin/users');
        const data = await res.json();
        const tbody = document.getElementById('users-tbody');
        tbody.innerHTML = '';
        (data.users || []).forEach(u => {
            const tr = document.createElement('tr');
            const isAdmin = u.role === 'admin';
            tr.innerHTML = `
                <td>${escapeHtml(u.username)}</td>
                <td><span class="badge ${isAdmin ? 'bg-warning text-dark' : 'bg-secondary'}">${isAdmin ? 'Админ' : 'Пользователь'}</span></td>
                <td class="text-end">
                    <div class="input-group input-group-sm d-inline-flex" style="width: 220px;">
                        <input type="password" class="form-control form-control-sm user-pass" data-uid="${u.id}" placeholder="Новый пароль">
                        <button class="btn btn-outline-primary btn-sm user-pass-set" data-uid="${u.id}" data-name="${escapeHtml(u.username)}">OK</button>
                    </div>
                    ${isAdmin ? '' : '<button class="btn btn-sm btn-outline-danger ms-1 user-del" data-uid="' + u.id + '" data-name="' + escapeHtml(u.username) + '"><i class="bi bi-trash"></i></button>'}
                </td>`;
            tbody.appendChild(tr);
            const delBtn = tr.querySelector('.user-del');
            if (delBtn) {
                delBtn.addEventListener('click', () => {
                    if (confirm('Удалить пользователя ' + delBtn.dataset.name + '?')) deleteUser(delBtn.dataset.uid);
                });
            }
            tr.querySelector('.user-pass-set').addEventListener('click', () => {
                const input = tr.querySelector('.user-pass');
                setUserPassword(tr.querySelector('.user-pass-set').dataset.uid, input.value);
                input.value = '';
            });
        });
    } catch (e) {
        console.error('Ошибка загрузки пользователей:', e);
    }
}

async function deleteUser(uid) {
    try {
        await apiFetch('/api/admin/users/' + uid, { method: 'DELETE' });
        loadUsers();
    } catch (e) { console.error(e); }
}

async function setUserPassword(uid, password) {
    if (!password) return;
    try {
        await apiFetch('/api/admin/users/' + uid + '/password', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        showToast('<i class="bi bi-check-lg me-2"></i>Пароль обновлён');
    } catch (e) { console.error(e); }
}

function addUser() {
    const name = document.getElementById('new-user-name').value.trim();
    const pass = document.getElementById('new-user-pass').value;
    if (!name || !pass) return;
    apiFetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: name, password: pass }),
    }).then(r => r.json()).then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
            return;
        }
        document.getElementById('new-user-name').value = '';
        document.getElementById('new-user-pass').value = '';
        loadUsers();
    }).catch(e => showToast(e.message, 'danger'));
}

async function loadMemoTemplateInfo() {
    try {
        const res = await apiFetch('/api/memo/template');
        const data = await res.json();
        const el = document.getElementById('memo-template-info');
        el.innerHTML = '<div>Путь: <code>' + escapeHtml(data.path || '') + '</code></div>' +
            '<div>Обновлён: ' + (data.updated || '—') + '</div>' +
            '<div>Поля: <code>' + escapeHtml((data.fields || []).map(f => f.key).join(', ')) + '</code></div>';
    } catch (e) {
        document.getElementById('memo-template-info').textContent = 'Ошибка: ' + e.message;
    }
}

let adminSyncJustTriggered = false;
let adminSyncShowResult = false;
let adminSyncHideTimer = null;

async function triggerSync(reset = false) {
    const btn = reset ? document.getElementById('btn-sync-reset') : document.getElementById('btn-sync');
    if (btn) btn.disabled = true;
    adminSyncJustTriggered = true;
    adminSyncShowResult = false;
    if (adminSyncHideTimer) {
        clearTimeout(adminSyncHideTimer);
        adminSyncHideTimer = null;
    }
    const container = document.getElementById('sync-progress-container');
    container.classList.remove('d-none');
    document.getElementById('adm-sync-status').textContent = 'Запуск синхронизации...';
    document.getElementById('adm-sync-percent').textContent = '0%';
    document.getElementById('adm-sync-progress-bar').style.width = '0%';
    try {
        await apiFetch('/api/admin/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reset }),
        });
        showToast(reset ? 'Сброс и синхронизация запущены' : 'Синхронизация запущена');
        setTimeout(updateSyncProgress, 400);
    } catch (e) {
        adminSyncJustTriggered = false;
        container.classList.add('d-none');
        showToast(e.message, 'danger');
    } finally {
        if (btn) btn.disabled = false;
    }
}

function updateSyncProgress() {
    apiFetch('/api/admin/info').then(r => r.json()).then(data => {
        const container = document.getElementById('sync-progress-container');
        if (data.is_syncing) {
            adminSyncJustTriggered = false;
            adminSyncShowResult = false;
            if (adminSyncHideTimer) {
                clearTimeout(adminSyncHideTimer);
                adminSyncHideTimer = null;
            }
            container.classList.remove('d-none');
            document.getElementById('adm-sync-status').textContent = data.status || 'Синхронизация...';
            document.getElementById('adm-sync-percent').textContent = (data.progress || 0) + '%';
            document.getElementById('adm-sync-progress-bar').style.width = (data.progress || 0) + '%';
        } else if (adminSyncJustTriggered || adminSyncShowResult) {
            adminSyncJustTriggered = false;
            adminSyncShowResult = true;
            document.getElementById('adm-sync-status').textContent = 'Синхронизация завершена: ' + (data.status || 'Готово');
            document.getElementById('adm-sync-percent').textContent = (data.progress || 100) + '%';
            document.getElementById('adm-sync-progress-bar').style.width = (data.progress || 100) + '%';
            if (!adminSyncHideTimer) {
                adminSyncHideTimer = setTimeout(() => {
                    adminSyncShowResult = false;
                    container.classList.add('d-none');
                    adminSyncHideTimer = null;
                }, 4000);
            }
        } else {
            container.classList.add('d-none');
        }
        loadAdminInfo();
    }).catch(() => {});
}

function collectConfig() {
    return {
        provider: document.getElementById('cfg-provider').value,
        url: document.getElementById('cfg-url').value,
        api_key: document.getElementById('cfg-api-key').value,
        llm: document.getElementById('cfg-llm').value,
        llm_embed: document.getElementById('cfg-llm-embed').value,
        llm_keywords: document.getElementById('cfg-llm-keywords').value,
        context_window: parseInt(document.getElementById('cfg-context-window').value) || 4096,
        chunk_size: parseInt(document.getElementById('cfg-chunk-size').value) || 256,
        chunk_overlap: parseInt(document.getElementById('cfg-chunk-overlap').value) || 50,
        similarity_top_k: parseInt(document.getElementById('cfg-similarity-top-k').value) || 10,
    };
}

async function saveConfig() {
    const status = document.getElementById('config-status');
    status.textContent = 'Сохранение...';
    try {
        const res = await apiFetch('/api/admin/config', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(collectConfig()),
        });
        const data = await res.json();
        if (data.error) {
            status.textContent = 'Ошибка: ' + data.error;
            showToast(data.error, 'danger');
            return;
        }
        status.textContent = 'Сохранено. Изменено: ' + (data.changed || []).join(', ');
        showToast('<i class="bi bi-check-lg me-2"></i>Конфигурация сохранена');
        loadAdminInfo();
    } catch (e) {
        status.textContent = 'Ошибка: ' + e.message;
        showToast(e.message, 'danger');
    }
}

async function resetConfig() {
    if (!confirm('Сбросить конфигурацию RAG System к дефолтам и пересинхронизировать индекс?')) return;
    try {
        const res = await apiFetch('/api/admin/config/reset', { method: 'POST' });
        const data = await res.json();
        if (data.error) {
            showToast(data.error, 'danger');
            return;
        }
        showToast('Конфигурация сброшена');
        location.reload();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

// === Расписание использования (запрет) ===
const SCHEDULE_DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

async function loadSchedule() {
    try {
        const res = await apiFetch('/api/admin/schedule');
        const data = await res.json();
        const list = document.getElementById('schedule-list');
        list.innerHTML = '';
        const items = data.restrictions || [];
        if (!items.length) {
            list.innerHTML = '<div class="small text-muted">Ограничений нет</div>';
            return;
        }
        items.forEach(r => {
            const days = (r.days || []).map(d => SCHEDULE_DAYS[d] || d).join(', ');
            const item = document.createElement('div');
            item.className = 'schedule-item';
            item.innerHTML = `
                <div class="d-flex align-items-start gap-2">
                    <div class="flex-grow-1">
                        <div class="fw-bold small">${escapeHtml(days)} ${escapeHtml(r.start_time)}–${escapeHtml(r.end_time)}
                            <span class="badge ${r.active ? 'bg-success' : 'bg-secondary'}">${r.active ? 'Активно' : 'Выкл'}</span>
                        </div>
                        <div class="small text-muted">${escapeHtml(r.message || '')}</div>
                    </div>
                    <div class="d-flex gap-1">
                        <button class="btn btn-sm btn-outline-secondary schedule-toggle" data-rid="${r.id}" title="Включить/выключить">
                            <i class="bi bi-power"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger schedule-del" data-rid="${r.id}" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>`;
            item.querySelector('.schedule-del').addEventListener('click', () => deleteRestriction(r.id));
            item.querySelector('.schedule-toggle').addEventListener('click', () => toggleRestriction(r.id, !r.active));
            list.appendChild(item);
        });
    } catch (e) {
        console.error('Ошибка загрузки расписания:', e);
    }
}

async function addRestriction() {
    const days = [...document.querySelectorAll('#schedule-days input:checked')].map(c => parseInt(c.value, 10));
    const start = document.getElementById('schedule-start').value;
    const end = document.getElementById('schedule-end').value;
    const message = document.getElementById('schedule-message').value.trim();
    if (!days.length) { showToast('Выберите дни недели', 'warning'); return; }
    if (!start || !end) { showToast('Укажите время начала и конца', 'warning'); return; }
    if (!message) { showToast('Укажите текст блокировки', 'warning'); return; }
    try {
        const res = await apiFetch('/api/admin/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days, start_time: start, end_time: end, message }),
        });
        const data = await res.json();
        if (data.error) { showToast(data.error, 'danger'); return; }
        document.querySelectorAll('#schedule-days input:checked').forEach(c => { c.checked = false; });
        document.getElementById('schedule-message').value = '';
        loadSchedule();
        showToast('<i class="bi bi-check-lg me-2"></i>Ограничение добавлено');
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

async function deleteRestriction(rid) {
    if (!confirm('Удалить ограничение расписания?')) return;
    try {
        await apiFetch('/api/admin/schedule/' + rid, { method: 'DELETE' });
        loadSchedule();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

async function toggleRestriction(rid, active) {
    try {
        await apiFetch('/api/admin/schedule/' + rid, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active }),
        });
        loadSchedule();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

// === Уведомления пользователям ===
async function loadAdminNotifications() {
    try {
        const res = await apiFetch('/api/admin/notifications');
        const data = await res.json();
        const list = document.getElementById('notifications-list');
        list.innerHTML = '';
        const items = data.notifications || [];
        if (!items.length) {
            list.innerHTML = '<div class="small text-muted">Уведомлений нет</div>';
            return;
        }
        items.forEach(n => {
            const item = document.createElement('div');
            item.className = 'notification-item';
            item.innerHTML = `
                <span class="small flex-grow-1">${escapeHtml(n.text)}</span>
                <button class="btn btn-sm btn-link text-danger p-0 notification-del" data-nid="${n.id}" title="Удалить">
                    <i class="bi bi-x-lg"></i>
                </button>`;
            item.querySelector('.notification-del').addEventListener('click', () => deleteNotification(n.id));
            list.appendChild(item);
        });
    } catch (e) {
        console.error('Ошибка загрузки уведомлений:', e);
    }
}

async function addNotification() {
    const input = document.getElementById('notification-input');
    const text = input.value.trim();
    if (!text) return;
    try {
        const res = await apiFetch('/api/admin/notifications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (data.error) { showToast(data.error, 'danger'); return; }
        input.value = '';
        loadAdminNotifications();
        showToast('<i class="bi bi-check-lg me-2"></i>Уведомление отправлено');
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

async function deleteNotification(nid) {
    if (!confirm('Удалить уведомление?')) return;
    try {
        await apiFetch('/api/admin/notifications/' + nid, { method: 'DELETE' });
        loadAdminNotifications();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

// === Сообщения от пользователей ===
async function loadAdminMessages() {
    try {
        const res = await apiFetch('/api/admin/messages');
        const data = await res.json();
        const list = document.getElementById('admin-messages-list');
        const badge = document.getElementById('admin-messages-badge');
        list.innerHTML = '';
        const items = data.messages || [];
        const unread = items.filter(m => !m.is_read).length;
        if (badge) {
            badge.textContent = unread;
            badge.classList.toggle('d-none', unread === 0);
        }
        if (!items.length) {
            list.innerHTML = '<div class="small text-muted">Сообщений нет</div>';
            return;
        }
        items.forEach(m => {
            const item = document.createElement('div');
            item.className = 'admin-message-item' + (m.is_read ? ' read' : '');
            item.innerHTML = `
                <div class="d-flex align-items-start gap-2">
                    <div class="flex-grow-1">
                        <div class="small fw-bold">${escapeHtml(m.username || '?')}
                            <span class="text-muted fw-normal">· ${escapeHtml((m.created_at || '').replace('T', ' ').slice(0, 16))}</span>
                            ${m.is_read ? '' : '<span class="badge bg-danger ms-1">новое</span>'}
                        </div>
                        <div class="small">${escapeHtml(m.text)}</div>
                    </div>
                    <div class="d-flex gap-1">
                        <button class="btn btn-sm btn-outline-secondary msg-read" data-mid="${m.id}" data-read="${m.is_read}"
                                title="${m.is_read ? 'Отметить непрочитанным' : 'Отметить прочитанным'}">
                            <i class="bi ${m.is_read ? 'bi-envelope' : 'bi-envelope-open'}"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger msg-del" data-mid="${m.id}" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>`;
            item.querySelector('.msg-read').addEventListener('click', () => setAdminMessageRead(m.id, !m.is_read));
            item.querySelector('.msg-del').addEventListener('click', () => deleteAdminMessage(m.id));
            list.appendChild(item);
        });
    } catch (e) {
        console.error('Ошибка загрузки сообщений:', e);
    }
}

async function setAdminMessageRead(mid, isRead) {
    try {
        await apiFetch('/api/admin/messages/' + mid + '/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_read: isRead }),
        });
        loadAdminMessages();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

async function deleteAdminMessage(mid) {
    if (!confirm('Удалить сообщение?')) return;
    try {
        await apiFetch('/api/admin/messages/' + mid, { method: 'DELETE' });
        loadAdminMessages();
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

// === Смена собственного пароля (админ) ===
async function changeOwnPassword() {
    const cur = document.getElementById('adm-pass-current').value;
    const newPass = document.getElementById('adm-pass-new').value;
    const confirmPass = document.getElementById('adm-pass-confirm').value;
    if (!cur || !newPass) { showToast('Заполните все поля', 'warning'); return; }
    if (newPass !== confirmPass) { showToast('Новые пароли не совпадают', 'warning'); return; }
    try {
        const res = await apiFetch('/api/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: cur, new_password: newPass }),
        });
        const data = await res.json();
        if (data.error) { showToast(data.error, 'danger'); return; }
        document.getElementById('adm-pass-current').value = '';
        document.getElementById('adm-pass-new').value = '';
        document.getElementById('adm-pass-confirm').value = '';
        showToast('<i class="bi bi-check-lg me-2"></i>Пароль изменён');
    } catch (e) {
        showToast(e.message, 'danger');
    }
}

function init() {
    loadAdminInfo();
    loadFolders();
    loadUsers();
    loadMemoTemplateInfo();
    loadSchedule();
    loadAdminNotifications();
    loadAdminMessages();

    document.getElementById('btn-sync').addEventListener('click', () => triggerSync(false));
    document.getElementById('btn-sync-reset').addEventListener('click', () => triggerSync(true));
    document.getElementById('folder-add-btn').addEventListener('click', addFolder);
    document.getElementById('folder-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addFolder();
    });
    document.getElementById('new-user-btn').addEventListener('click', addUser);
    document.getElementById('new-user-pass').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addUser();
    });
    document.getElementById('schedule-add-btn').addEventListener('click', addRestriction);
    document.getElementById('notification-add-btn').addEventListener('click', addNotification);
    document.getElementById('notification-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addNotification();
    });
    document.getElementById('adm-pass-btn').addEventListener('click', changeOwnPassword);
    document.getElementById('memo-template-reload').addEventListener('click', async () => {
        try {
            await apiFetch('/api/admin/memo/template/reload', { method: 'POST' });
            loadMemoTemplateInfo();
            showToast('Шаблон перечитан');
        } catch (e) { showToast(e.message, 'danger'); }
    });
    document.getElementById('memo-template-file').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        try {
            await apiFetch('/api/admin/memo/template', { method: 'POST', body: fd });
            loadMemoTemplateInfo();
            showToast('Шаблон обновлён');
        } catch (err) { showToast(err.message, 'danger'); }
    });
    document.getElementById('config-form').addEventListener('submit', (e) => {
        e.preventDefault();
        saveConfig();
    });
    document.getElementById('btn-config-reset').addEventListener('click', resetConfig);

    adminSyncTimer = setInterval(updateSyncProgress, 500);
}

document.addEventListener('DOMContentLoaded', init);