// === Уведомления администратора: сверху, скрываются по клику или крестику ===
const Notifications = {
    async init() {
        const container = document.getElementById('notifications-container');
        if (!container) return;
        try {
            const res = await fetch('/api/notifications');
            if (!res.ok) return;
            const data = await res.json();
            (data.notifications || []).forEach(n => this.render(container, n));
        } catch (e) {
            console.error('Ошибка загрузки уведомлений:', e);
        }
    },

    render(container, n) {
        const el = document.createElement('div');
        el.className = 'notification-banner';
        el.innerHTML = '<div class="notification-text">' + escapeHtml(n.text) + '</div>' +
            '<button class="notification-close" title="Закрыть"><i class="bi bi-x-lg"></i></button>';
        const dismiss = () => {
            el.remove();
            fetch('/api/notifications/' + n.id + '/dismiss', { method: 'POST' }).catch(() => {});
        };
        el.addEventListener('click', dismiss);
        container.appendChild(el);
    },
};
