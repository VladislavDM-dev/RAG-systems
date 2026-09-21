// === Чат: сообщения, SSE-стриминг, команды ===
const Chat = {
    isGenerating: false,
    inputsUnlocked: false,
    serverReady: false,
    last_question: "",

    COMMANDS: [
        { cmd: '/create', desc: 'Служебная записка по теме: /create тема' },
        { cmd: '/memos', desc: 'Список служебных записок: /memos тема' },
        { cmd: '/new', desc: 'Начать новый диалог' },
        { cmd: '/clear', desc: 'Очистить всю историю диалогов и ответов' },
        { cmd: '/help', desc: 'Показать список команд' },
    ],

    init() {
        this.questionInput = document.getElementById('question-input');
        this.sendBtn = document.getElementById('send-btn');
        this.systemStatus = document.getElementById('system-status');
        this.chatContainer = document.getElementById('chat-container');

        this.sendBtn.addEventListener('click', () => this.sendQuery());
        this.questionInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const wrap = document.getElementById('command-menu-wrap');
                if (wrap && !wrap.classList.contains('d-none')) {
                    e.preventDefault();
                    const first = wrap.querySelector('.command-menu-item');
                    if (first) { first.click(); return; }
                }
                this.sendQuery();
            }
        });

        this.questionInput.addEventListener('input', () => {
            const v = this.questionInput.value.trim();
            if (v.startsWith('/') && !v.includes(' ')) {
                this.showCommandMenu(v);
            } else {
                this.hideCommandMenu();
            }
        });
        this.questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.hideCommandMenu();
            if (e.key === 'Backspace') {
                if (this.questionInput.value.trim().length <= 1) this.hideCommandMenu();
            }
        });
        document.addEventListener('click', (e) => {
            const wrap = document.getElementById('command-menu-wrap');
            if (wrap && !wrap.contains(e.target) && e.target.id !== 'question-input') {
                this.hideCommandMenu();
            }
            const copyBtn = e.target.closest('.memo-copy');
            if (copyBtn) copyText(copyBtn.dataset.path, copyBtn);
            const favBtn = e.target.closest('.memo-fav');
            if (favBtn) this.saveMemoToFavorites(favBtn);
        });
    },

unlockInputs(unlock) {
        if (unlock && !this.serverReady) return;
        this.questionInput.disabled = !unlock;
        this.sendBtn.disabled = !unlock;
        this.inputsUnlocked = unlock;
        if (unlock) {
            this.questionInput.placeholder = "Введите ваш вопрос...";
            this.questionInput.focus();
        }
    },

    appendMessage(text, isUser, sources = [], extraClass = '') {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'message-row ' + (isUser ? 'user' : 'bot') + ' ' + extraClass;
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        bubbleDiv.appendChild(contentDiv);

        let pureText = text || '';

        if (!isUser) {
            const saveBtn = document.createElement('button');
            saveBtn.className = 'btn btn-sm btn-outline-primary mb-2';
            saveBtn.innerHTML = '<i class="bi bi-bookmark-plus"></i> Сохранить в избранное';
            saveBtn.onclick = () => {
                History.saveAnswerToFavorites(this.last_question, pureText, []);
            };
            bubbleDiv.appendChild(saveBtn);
        }

        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources-list';
        sourcesDiv.style.display = 'none';
        bubbleDiv.appendChild(sourcesDiv);

        rowDiv.appendChild(bubbleDiv);
        this.chatContainer.appendChild(rowDiv);
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;

        const renderContent = (txt) => {
            contentDiv.innerHTML = renderMarkdown(txt || '');
        };
        if (text) renderContent(text);

        return {
            row: rowDiv,
            bubble: bubbleDiv,
            content: contentDiv,
            sourcesContainer: sourcesDiv,
            updateText: function(txt) {
                pureText = txt || '';
                renderContent(pureText);
            },
            appendText: function(txt) {
                pureText += txt || '';
                renderContent(pureText);
                const cc = document.getElementById('chat-container');
                if (cc) cc.scrollTop = cc.scrollHeight;
            },
            showSources: function(list) {
                if (!list || list.length === 0) return;
                let html = '<strong style="display:block; margin-top: 5px;">&#128218; Источники:</strong><ul>';
                list.forEach(src => {
                    if (typeof src === 'object' && src !== null) {
                        if (src.button) {
                            html += '<li>' + src.button + '</li>';
                        } else if (src.file_path) {
                            const label = src.file_name || src.file_path;
                            const fp = String(src.file_path).replace(/"/g, '&#34;').replace(/&/g, '&amp;');
                            html += '<li><button type="button" class="btn btn-sm btn-outline-primary source-file-btn" data-file-path="' + fp + '">&#128196; ' + label + '</button></li>';
                        } else {
                            html += '<span class="file-badge">&#128196; ' + src.file_name + '</span><br>';
                        }
                    } else {
                        html += '<span class="file-badge">&#128196; ' + src + '</span><br>';
                    }
                });
                html += '</ul>';
                sourcesDiv.innerHTML = html;
sourcesDiv.querySelectorAll('.source-file-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const path = btn.dataset.filePath;
                        if (path) Chat.openFileModal(path);
                    });
                });
                sourcesDiv.style.display = 'block';
            },
            addDots: function() {
                contentDiv.classList.add('typing-indicator');
                contentDiv.innerHTML = '';
                pureText = '';
            },
            removeDots: function() {
                contentDiv.classList.remove('typing-indicator');
            }
        };
    },

    // === Команды ===
    showCommandMenu(filter) {
        const wrap = document.getElementById('command-menu-wrap');
        if (!wrap) return;
        const menu = document.getElementById('command-menu');
        const query = (filter || '').toLowerCase();
        const items = query ? this.COMMANDS.filter(c => c.cmd.toLowerCase().startsWith(query)) : this.COMMANDS;
        if (!items.length) { wrap.classList.add('d-none'); return; }
        menu.innerHTML = items.map(c =>
            '<div class="command-menu-item" data-cmd="' + c.cmd + '">' +
            '<span class="cmd-name">' + c.cmd + '</span>' +
            '<span class="cmd-desc">' + c.desc + '</span></div>').join('');
        wrap.classList.remove('d-none');
        menu.querySelectorAll('.command-menu-item').forEach(el => {
            el.addEventListener('click', () => this.pickCommand(el.dataset.cmd));
            el.addEventListener('mousedown', (e) => e.preventDefault());
        });
    },

    hideCommandMenu() {
        const wrap = document.getElementById('command-menu-wrap');
        if (wrap) wrap.classList.add('d-none');
    },

    pickCommand(cmd) {
        this.hideCommandMenu();
        if (cmd === '/create' || cmd === '/memos') {
            this.questionInput.value = cmd + ' ';
            this.questionInput.focus();
            return;
        }
        this.questionInput.value = '';
        if (cmd === '/new') {
            this.startNewChat();
        } else if (cmd === '/clear') {
            History.clearAll();
        } else if (cmd === '/help') {
            this.showCommandsHelp();
        }
    },

    showCommandsHelp() {
        const lines = ['**Команды чата:**'];
        this.COMMANDS.forEach(c => {
            lines.push('- `' + c.cmd + '` — ' + c.desc);
        });
        this.appendMessage(lines.join('\n'), false);
    },

    sendQuery() {
        const text = this.questionInput.value.trim();
        if (!text) return;
        if (this.isGenerating || !this.inputsUnlocked) return;
        if (!this.serverReady) {
            showToast('Сервер ещё не готов — дождитесь окончания синхронизации', 'warning');
            return;
        }
        const low = text.toLowerCase();
        if (low === '/help') { this.questionInput.value = ''; this.showCommandsHelp(); return; }
        if (low === '/new') { this.questionInput.value = ''; this.startNewChat(); return; }
        if (low === '/clear') { this.questionInput.value = ''; History.clearAll(); return; }
        if (low.startsWith('/create')) { this.questionInput.value = ''; MemoWizard.start(text); return; }
        if (low.startsWith('/memos')) { this.questionInput.value = ''; this.sendMemosQuery(text); return; }
        if (typeof MemoWizard !== 'undefined' && MemoWizard.isActive()) {
            this.questionInput.value = '';
            MemoWizard.handleInput(text);
            return;
        }
        this.questionInput.value = '';
        this.sendServerQuery(text);
    },

    async sendMemosQuery(text) {
        const query = text.replace(/^\/memos\s*/i, '').trim();
        if (!query) {
            this.appendMessage('Укажите тему для поиска: `/memos тема`', false);
            return;
        }
        await this.sendServerQuery(query, null, { memos_paged: true, temperature: 0.0 });
    },

async sendServerQuery(question, systemPrompt = null, options = {}) {
        if (this.isGenerating) return;
        if (!this.serverReady) {
            showToast('Сервер ещё не готов — дождитесь окончания синхронизации', 'warning');
            return;
        }
        this.isGenerating = true;
        this.unlockInputs(false);
        this.last_question = question;
        this.appendMessage(question, true);

        const botMsg = this.appendMessage('', false, []);
        botMsg.addDots();
        let fullAnswer = '';
        let sourcesData = [];
        let gotAnswer = false;

try {
            const body = { prompt: question };
            if (systemPrompt) body.system_prompt = systemPrompt;
            if (options.top_k) body.top_k = options.top_k;
            if (options.temperature != null) body.temperature = options.temperature;
            if (options.memos_paged) body.memos_paged = true;
            await streamSSE('/api/chat/stream', body, {
                onSources: (s) => { sourcesData = s; },
                onToken: (t) => {
                    if (fullAnswer === '') botMsg.removeDots();
                    fullAnswer += t;
                    botMsg.appendText(t);
                },
onDone: async (data) => {
                    gotAnswer = true;
                    if (!fullAnswer && data.answer) {
                        fullAnswer = data.answer;
                        botMsg.removeDots();
                        botMsg.updateText(fullAnswer);
                    }
                    const sources = data.sources || sourcesData;
                    botMsg.showSources(sources);
                    botMsg.removeDots();
                    await this.saveMessage(question, fullAnswer, sources);
                },
                onError: (e) => {
                    botMsg.removeDots();
                    botMsg.updateText('Ошибка: ' + e.data);
                },
            });
            if (!gotAnswer && fullAnswer) {
                botMsg.removeDots();
                botMsg.updateText(fullAnswer);
            }
        } catch (e) {
            botMsg.removeDots();
            botMsg.updateText('Ошибка соединения: ' + e.message);
        } finally {
            this.isGenerating = false;
            this.unlockInputs(true);
        }
    },

memoListHtml(memos, questionLabel) {
        const memosArr = Array.isArray(memos) ? memos : [];
        const items = memosArr.map(m => {
            const title = (m.file_name || '').replace(/\.docx$/i, '');
            const body = (m.text || '').trim();
            const path = m.file_path || '';
            return '<li>' + escapeHtml(title) +
                '<div class="memo-meta"><span class="memo-path">' + escapeHtml(path) + '</span>' +
                '<button type="button" class="btn btn-sm btn-outline-secondary memo-copy" data-path="' + escapeHtml(path) + '">Скопировать путь</button>' +
                '<button type="button" class="btn btn-sm btn-outline-primary memo-fav" data-title="' + escapeHtml(title) + '" data-path="' + escapeHtml(path) + '">Сохр. в избранное</button></div>' +
                '<div class="memo-list-body">' + escapeHtml(body) + '</div></li>';
        }).join('\n');
        return '<div class="memo-list"><h6><b>Служебные записки по запросу "' + (questionLabel || '') + '" (' + memosArr.length + '):</b></h6><ol>' + items + '</ol></div>';
    },

    async saveMemoToFavorites(btn) {
        const title = btn.dataset.title || '';
        const path = btn.dataset.path || '';
        const memo = btn.closest('li')?.querySelector('.memo-list-body')?.textContent || '';
        const question = 'Служебная записка: ' + title;
        await History.saveAnswerToFavorites(question, memo || question, [
            { file_name: title + '.docx', file_path: path, score: null }
        ]);
        const old = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-bookmark-check-fill"></i> В избранном';
        btn.classList.add('btn-success');
        btn.classList.remove('btn-outline-primary');
        setTimeout(() => { btn.innerHTML = old; btn.classList.remove('btn-success'); btn.classList.add('btn-outline-primary'); }, 2000);
    },

    // === Сообщения ===
    async ensureConversation() {
        if (History.activeConversationId) return;
        try {
            const res = await apiFetch('/api/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: this.last_question }),
            });
            const data = await res.json();
            History.activeConversationId = data.conversation.id;
        } catch (e) { console.error('Ошибка создания диалога:', e); }
    },

    async saveMessage(question, answer, sources, options = {}) {
        try {
            await this.ensureConversation();
            const convId = History.activeConversationId;
            await apiFetch('/api/messages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_id: convId, role: 'user', content: question }),
            });
            await apiFetch('/api/messages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    conversation_id: convId,
                    role: 'bot',
                    content: answer,
                    sources: sources,
                    memo_data: options.memoList || null,
                }),
            });
            History.loadConversations(true);
        } catch (e) { console.error('Ошибка сохранения сообщений:', e); }
    },

    async restoreLastConversation() {
        try {
            const res = await apiFetch('/api/conversations?per_page=1');
            const data = await res.json();
            const last = (data.conversations || [])[0];
            if (last) {
                await this.loadConversation(last.id);
            }
        } catch (e) {
            console.error('Ошибка восстановления последнего диалога:', e);
        }
    },

    async loadConversation(convId) {
        try {
            const res = await apiFetch('/api/conversations/' + convId);
            const data = await res.json();
            History.activeConversationId = convId;
            this.last_question = data.conversation.title || '';
            this.chatContainer.innerHTML = '';
            const messages = data.messages || [];
            messages.forEach(msg => {
                const msgObj = this.appendMessage(msg.content, msg.role === 'user');
                if (msg.role === 'bot' && msg.memo_data && msg.memo_data.length) {
                    msgObj.content.innerHTML = this.memoListHtml(msg.memo_data, this.last_question);
                } else if (msg.role === 'bot' && msg.sources && msg.sources.length > 0) {
                    msgObj.showSources(msg.sources);
                }
            });
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
            this.isGenerating = false;
            this.unlockInputs(true);
            History.loadConversations(true);
            document.querySelectorAll('.conversation-item').forEach(el => {
                el.classList.toggle('active', el.dataset.id === String(convId));
            });
        } catch (e) {
            console.error('Ошибка загрузки диалога:', e);
        }
    },

    async loadFavorite(favId) {
        try {
            const res = await apiFetch('/api/conversations?per_page=1');
            await res.json();
            const favRes = await apiFetch('/api/favorites?per_page=500');
            const favData = await favRes.json();
            const fav = (favData.favorites || []).find(f => f.id === favId);
            if (!fav) return;
            this.chatContainer.innerHTML = '';
            this.appendMessage('[Избранное] ' + fav.title, true);
            const botMsg = this.appendMessage(fav.content || '', false);
            if (fav.sources && fav.sources.length > 0) botMsg.showSources(fav.sources);
        } catch (e) { console.error('Ошибка загрузки избранного:', e); }
    },

    clearChat() {
        this.chatContainer.innerHTML = '';
        History.activeConversationId = null;
        this.last_question = '';
        if (this.questionInput) this.questionInput.value = '';
        this.appendMessage('Новый диалог начат. Вы можете задать вопрос.', false);
    },

    startNewChat() {
        this.clearChat();
    },

    // === Модальное окно файла ===
    openFileModal(filePath) {
        document.getElementById('filePath').value = filePath;
        const modal = new bootstrap.Modal(document.getElementById('fileModal'));
        modal.show();
        this.parseFile(filePath);
    },

    async parseFile(filePath) {
        const spinner = document.getElementById('spinner');
        const resultContent = document.getElementById('result-content');
        const errorMsg = document.getElementById('error-message');
        errorMsg.classList.add('d-none');
        resultContent.innerHTML = '';
        spinner.classList.remove('d-none');
        try {
            const res = await apiFetch('/api/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath }),
            });
            const data = await res.json();
            if (data.ok) {
                resultContent.innerHTML = renderMarkdown(data.content);
            } else {
                errorMsg.textContent = data.error || 'Ошибка при обработке';
                errorMsg.classList.remove('d-none');
            }
        } catch (err) {
            errorMsg.textContent = 'Ошибка сети: ' + err.message;
            errorMsg.classList.remove('d-none');
        } finally {
            spinner.classList.add('d-none');
        }
    },
};
