// === История: загрузка, пагинация, переключение чатов ===
const History = {
    activeConversationId: null,
    activeTab: 'conversations',
    convPage: 1,
    favPage: 1,
    convHasMore: true,
    favHasMore: true,

    async loadConversations(reset = false) {
        if (reset) { this.convPage = 1; this.convHasMore = true; }
        if (!this.convHasMore) return;
        const loading = document.getElementById('history-loading');
        if (loading) loading.classList.remove('d-none');
        try {
            const params = new URLSearchParams({ page: this.convPage, per_page: 50 });
            const res = await apiFetch('/api/conversations?' + params);
            const data = await res.json();
            const container = document.getElementById('conversationsTab');
            if (reset) container.innerHTML = '';
            this.renderConversations(container, data.conversations || []);
            this.convHasMore = (data.page || 1) < (data.pages || 1);
            this.convPage = (data.page || 1) + 1;
        } catch (e) {
            console.error('Ошибка загрузки диалогов:', e);
        } finally {
            if (loading) loading.classList.add('d-none');
        }
    },

    async loadFavorites(reset = false) {
        if (reset) { this.favPage = 1; this.favHasMore = true; }
        if (!this.favHasMore) return;
        try {
            const params = new URLSearchParams({ page: this.favPage, per_page: 50 });
            const res = await apiFetch('/api/favorites?' + params);
            const data = await res.json();
            const container = document.getElementById('favoritesTab');
            if (reset) container.innerHTML = '';
            this.renderFavorites(container, data.favorites || []);
            this.favHasMore = (data.page || 1) < (data.pages || 1);
            this.favPage = (data.page || 1) + 1;
        } catch (e) {
            console.error('Ошибка загрузки избранного:', e);
        }
    },

    renderConversations(container, conversations) {
        if (container.children.length === 0 && conversations.length === 0) {
            container.innerHTML = `
                <div class="empty-history">
                    <div class="empty-icon">💬</div>
                    <p>У вас пока нет сохранённых чатов</p>
                    <small class="text-muted">Начните диалог, чтобы сохранить его в историю</small>
                </div>`;
            return;
        }
        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (conv.id === this.activeConversationId) item.classList.add('active');
            const title = conv.title || 'Без названия';
            item.dataset.id = conv.id;

            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div class="conv-title text-truncate flex-grow-1" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
                    <div class="btn-group ms-2 flex-nowrap">
                        <button class="btn btn-sm btn-link p-0 edit-chat-btn" data-id="${conv.id}" title="Переименовать"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-link text-danger p-0 delete-chat-btn" data-id="${conv.id}" title="Удалить"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
                <div class="conv-meta small text-muted d-flex justify-content-between">
                    <span>${new Date(conv.updated_at || conv.created_at).toLocaleDateString('ru-RU')}</span>
                    <span>${formatTimeAgo(new Date(conv.updated_at || conv.created_at).getTime())}</span>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.closest('.btn-group')) return;
                Chat.loadConversation(conv.id);
            });
            item.querySelector('.edit-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.startRename(item, conv.id, title, (newName) => this.renameConversation(conv.id, newName));
            });
            item.querySelector('.delete-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Удалить диалог "${title}"?`)) {
                    this.deleteConversation(conv.id);
                }
            });
            container.appendChild(item);
        });
    },

    renderFavorites(container, favorites) {
        if (container.children.length === 0 && favorites.length === 0) {
            container.innerHTML = `
                <div class="empty-history">
                    <div class="empty-icon">💡</div>
                    <p>У вас пока нет избранных ответов</p>
                    <small class="text-muted">Отмечайте важные ответы, чтобы сохранить их здесь</small>
                </div>`;
            return;
        }
        favorites.forEach(fav => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            const title = fav.title || 'Без названия';
            item.dataset.id = fav.id;

            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div class="conv-title text-truncate flex-grow-1" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
                    <div class="btn-group ms-2 flex-nowrap">
                        <button class="btn btn-sm btn-link text-danger p-0 delete-fav-btn" data-id="${fav.id}" title="Удалить"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
                <div class="conv-meta text-muted small d-flex justify-content-between">
                    <span>${new Date(fav.created_at).toLocaleDateString()}</span>
                    <span>${formatTimeAgo(new Date(fav.created_at).getTime())}</span>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.closest('.delete-fav-btn')) return;
                Chat.loadFavorite(fav.id);
            });
            item.querySelector('.delete-fav-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Удалить "${title}"?`)) {
                    this.deleteFavorite(fav.id);
                }
            });
            container.appendChild(item);
        });
    },

    startRename(itemEl, id, currentTitle, onUpdate) {
        const titleDiv = itemEl.querySelector('.conv-title');
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.value = currentTitle || '';
        input.style.fontSize = '0.85em';
        titleDiv.innerHTML = '';
        titleDiv.appendChild(input);
        input.focus();
        input.select();
        const save = () => {
            const newName = input.value.trim();
            if (newName) onUpdate(newName);
            input.remove();
            this.loadConversations(true);
        };
        input.addEventListener('blur', save);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') input.blur();
            if (e.key === 'Escape') input.remove();
        });
    },

    async renameConversation(id, newName) {
        try {
            await apiFetch('/api/conversations/' + id, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newName }),
            });
            this.loadConversations(true);
        } catch (e) {
            console.error('Ошибка переименования диалога:', e);
        }
    },

    async deleteConversation(id) {
        try {
            await apiFetch('/api/conversations/' + id, { method: 'DELETE' });
            if (this.activeConversationId === id) {
                this.activeConversationId = null;
                Chat.clearChat();
            }
            this.loadConversations(true);
        } catch (e) {
            console.error('Ошибка удаления диалога:', e);
        }
    },

    async deleteFavorite(id) {
        try {
            await apiFetch('/api/favorites/' + id, { method: 'DELETE' });
            this.loadFavorites(true);
        } catch (e) {
            console.error('Ошибка удаления избранного:', e);
        }
    },

    async saveAnswerToFavorites(title, content, sources, memoData) {
        try {
            await apiFetch('/api/favorites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, content, sources, memo_data: memoData }),
            });
            this.loadFavorites(true);
            showToast('<i class="bi bi-bookmark-check-fill me-2"></i>Сохранено в избранное');
        } catch (e) {
            console.error('Ошибка сохранения в избранное:', e);
        }
    },

    switchTab(tabName) {
        this.activeTab = tabName;
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        document.getElementById('conversationsTab').style.display = tabName === 'conversations' ? 'block' : 'none';
        document.getElementById('favoritesTab').style.display = tabName === 'favorites' ? 'block' : 'none';
        if (tabName === 'favorites') {
            this.loadFavorites(true);
        }
    },

    async clearAll() {
        if (!confirm('Очистить всю историю диалогов и избранных ответов?')) return;
        try {
            const conversations = await (await apiFetch('/api/conversations?per_page=500')).json();
            for (const c of conversations.conversations || []) {
                await apiFetch('/api/conversations/' + c.id, { method: 'DELETE' });
            }
            const favorites = await (await apiFetch('/api/favorites?per_page=500')).json();
            for (const f of favorites.favorites || []) {
                await apiFetch('/api/favorites/' + f.id, { method: 'DELETE' });
            }
            Chat.clearChat();
            this.loadConversations(true);
            this.loadFavorites(true);
        } catch (e) {
            console.error('Ошибка очистки истории:', e);
        }
    },
};