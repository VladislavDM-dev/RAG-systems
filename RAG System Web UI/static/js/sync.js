// === Мониторинг синхронизации RAG ===
const Sync = {
    wasSyncing: false,
    dismissed: false,
    restrictionShown: false,
    timer: null,

    init() {
        const dismissBtn = document.getElementById('sync-dismiss');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', () => {
                document.getElementById('sync-overlay').classList.remove('active');
                this.dismissed = true;
            });
        }
        const overlay = document.getElementById('sync-overlay');
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay && !this.wasSyncing) {
                    overlay.classList.remove('active');
                    this.dismissed = true;
                }
            });
        }
    },

    show() {
        const overlay = document.getElementById('sync-overlay');
        if (!overlay) return;
        overlay.classList.add('active');
        const status = document.getElementById('sync-status-text');
        if (status) status.textContent = 'Синхронизация...';
    },

    hide(isReady = true) {
        if (this.dismissed && !this.wasSyncing) return;
        document.getElementById('sync-overlay').classList.remove('active');
        const status = Chat.systemStatus;
        if (status) {
            if (isReady) {
                status.textContent = 'Готов к работе';
                status.className = 'text-success fw-bold';
            } else {
                status.textContent = 'Ошибка инициализации';
                status.className = 'text-danger fw-bold';
            }
        }
    },

    async check() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            const overlay = document.getElementById('sync-overlay');
            const statusText = document.getElementById('sync-status-text');
            const percentText = document.getElementById('sync-percent-text');

            Chat.serverReady = !data.is_syncing && !!data.initialized && !data.restricted;

            if (data.is_syncing || !data.initialized) {
                this.wasSyncing = true;
                if (!overlay.classList.contains('active') && !this.dismissed) {
                    this.show();
                }
                if (statusText) statusText.textContent = data.status || 'Синхронизация...';
                const progress = Number(data.progress) || 0;
                const bar = document.getElementById('sync-progress-bar');
                if (bar) bar.style.width = progress + '%';
                const miniBar = document.getElementById('sync-progress-mini');
                if (miniBar) miniBar.classList.toggle('d-none', progress >= 100);
            } else {
                const wasSyncing = this.wasSyncing;
                this.wasSyncing = false;
                if (overlay.classList.contains('active')) {
                    this.hide(true);
                    if (wasSyncing) {
                        setTimeout(() => {
                            Chat.appendMessage('База знаний загружена и готова к работе!', false);
                        }, 500);
                        this.dismissed = false;
                    }
                }
                if (data.restricted) {
                    this.applyRestriction(data.restriction_message);
                } else if (data.initialized && !Chat.inputsUnlocked && !Chat.isGenerating) {
                    Chat.unlockInputs(true);
                    const status = Chat.systemStatus;
                    if (status) {
                        status.textContent = 'Готов к работе';
                        status.className = 'text-success fw-bold';
                    }
                }
            }
        } catch (e) {
            console.error('Ошибка проверки статуса:', e);
            Chat.serverReady = false;
            const status = Chat.systemStatus;
            if (status) {
                status.textContent = 'Ошибка соединения';
                status.className = 'text-danger fw-bold';
            }
            Chat.unlockInputs(false);
        }
    },

    applyRestriction(message) {
        Chat.unlockInputs(false);
        Chat.serverReady = false;
        const status = Chat.systemStatus;
        if (status) {
            status.textContent = message || 'Доступ ограничен по расписанию';
            status.className = 'text-danger fw-bold';
        }
        if (this.restrictionShown) return;
        this.restrictionShown = true;
        const banner = document.getElementById('restriction-banner');
        if (!banner) return;
        banner.textContent = message || 'Доступ к системе временно ограничен по расписанию.';
        banner.classList.remove('d-none');
    },

    start() {
        this.init();
        this.check();
        this.timer = setInterval(() => this.check(), 500);
    },
};