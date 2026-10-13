// === Инициализация приложения ===
document.addEventListener('DOMContentLoaded', () => {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(tooltipTriggerEl => {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    Chat.init();
    History.loadConversations(true);
    Chat.restoreLastConversation();

    MemoWizard.restoreSession();

    Notifications.init();

    const newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn) newChatBtn.addEventListener('click', () => Chat.startNewChat());

    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    if (clearHistoryBtn) clearHistoryBtn.addEventListener('click', () => History.clearAll());

    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.addEventListener('click', () => History.switchTab(btn.dataset.tab));
    });

    const copyButton = document.getElementById('copyButton');
    if (copyButton) {
        copyButton.addEventListener('click', () => {
            copyText(document.getElementById('filePath').value, copyButton);
        });
    }

    // Сообщение администратору об ошибке
    const feedbackBtn = document.getElementById('feedback-send-btn');
    if (feedbackBtn) {
        feedbackBtn.addEventListener('click', async () => {
            const textarea = document.getElementById('feedback-text');
            const text = textarea.value.trim();
            if (!text) { showToast('Опишите проблему', 'warning'); return; }
            feedbackBtn.disabled = true;
            try {
                const res = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text }),
                });
                const data = await res.json();
                if (!res.ok || data.error) {
                    showToast(data.error || 'Ошибка отправки', 'danger');
                    return;
                }
                textarea.value = '';
                bootstrap.Modal.getInstance(document.getElementById('feedbackModal'))?.hide();
                showToast('<i class="bi bi-check-lg me-2"></i>Сообщение отправлено администратору');
            } catch (e) {
                showToast(e.message, 'danger');
            } finally {
                feedbackBtn.disabled = false;
            }
        });
    }

    // Смена пароля (модалка пользователя)
    const passwordBtn = document.getElementById('password-save-btn');
    if (passwordBtn) {
        passwordBtn.addEventListener('click', async () => {
            const cur = document.getElementById('password-current').value;
            const newPass = document.getElementById('password-new').value;
            const confirmPass = document.getElementById('password-confirm').value;
            if (!cur || !newPass) { showToast('Заполните все поля', 'warning'); return; }
            if (newPass !== confirmPass) { showToast('Новые пароли не совпадают', 'warning'); return; }
            passwordBtn.disabled = true;
            try {
                const res = await fetch('/api/password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: cur, new_password: newPass }),
                });
                const data = await res.json();
                if (!res.ok || data.error) {
                    showToast(data.error || 'Ошибка смены пароля', 'danger');
                    return;
                }
                document.getElementById('password-current').value = '';
                document.getElementById('password-new').value = '';
                document.getElementById('password-confirm').value = '';
                bootstrap.Modal.getInstance(document.getElementById('passwordModal'))?.hide();
                showToast('<i class="bi bi-check-lg me-2"></i>Пароль изменён');
            } catch (e) {
                showToast(e.message, 'danger');
            } finally {
                passwordBtn.disabled = false;
            }
        });
    }

    // Бесконечная прокрутка истории
    const historyContent = document.getElementById('historyContent');
    historyContent.addEventListener('scroll', () => {
        if (historyContent.scrollTop + historyContent.clientHeight >= historyContent.scrollHeight - 50) {
            if (History.activeTab === 'conversations') {
                History.loadConversations();
            } else {
                History.loadFavorites();
            }
        }
    });

    Sync.start();
});