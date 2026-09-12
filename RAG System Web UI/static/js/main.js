// === Глобальные переменные ===
let activeConversationId = null;
let activeAnswerId = null;

let isGenerating = false;
let inputsUnlocked = false;
let last_question = "";

const questionInput = document.getElementById('question-input');
const sendBtn = document.getElementById('send-btn');
const systemStatus = document.getElementById('system-status');

// === Управление полями ===

function unlockInputs(unlock) {
    questionInput.disabled = !unlock;
    sendBtn.disabled = !unlock;
    inputsUnlocked = unlock;
    if (unlock) {
        questionInput.placeholder = "Введите ваш вопрос...";
        questionInput.focus();
    }
}

// === Вспомогательные функции ===

function generateUUID() {
    let d = new Date().getTime();
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
        d += performance.now();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = (d + Math.random() * 16) % 16 | 0;
        d = Math.floor(d / 16);
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTimeAgo(ts) {
    const diffMs = Date.now() - (ts || Date.now());
    const diffMins = Math.max(0, Math.floor(diffMs / 60000));
    if (diffMins < 1) return 'только что';
    if (diffMins < 60) return `${diffMins} мин назад`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)} ч назад`;
    return `${Math.floor(diffMins / 1440)} дн назад`;
}

// === Сообщения ===

function appendMessage(text, isUser, sources = []) {
    const rowDiv = document.createElement('div');
    rowDiv.className = `message-row ${isUser ? 'user' : 'bot'}`;
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
        saveBtn.onclick = () => saveAnswerToFavorites(last_question, pureText, []);
        bubbleDiv.appendChild(saveBtn);
    }

    const sourcesDiv = document.createElement('div');
    sourcesDiv.className = 'sources-list';
    sourcesDiv.style.display = 'none';
    bubbleDiv.appendChild(sourcesDiv);

    rowDiv.appendChild(bubbleDiv);
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer) chatContainer.appendChild(rowDiv);
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;

    function renderContent(txt) {
        try {
            contentDiv.innerHTML = marked.parse(txt || '');
        } catch (e) {
            contentDiv.innerHTML = (txt || '').replace(/\n/g, '<br>');
        }
    }

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
        },
        showSources: function(list) {
            if (!list || list.length === 0) return;
            let html = '<strong style="display:block; margin-top: 5px;">📚 Источники:</strong><ul>';
            list.forEach(src => {
                if (typeof src === 'object' && src !== null) {
                    if (src.button) {
                        html += `<li>${src.button}</li>`;
                    } else if (src.file_path) {
                        const label = src.file_name || src.file_path;
                        const fp = String(src.file_path).replace(/"/g, '&#34;').replace(/&/g, '&amp;');
                        html += `<li><button type="button" class="btn btn-sm btn-outline-primary source-file-btn" data-file-path="${fp}">📄 ${label}</button></li>`;
                    } else {
                        html += `<span class="file-badge">📄 ${src.file_name}</span><br>`;
                    }
                } else {
                    html += `<span class="file-badge">📄 ${src}</span><br>`;
                }
            });
            html += '</ul>';
            sourcesDiv.innerHTML = html;
            sourcesDiv.querySelectorAll('.source-file-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const path = btn.dataset.filePath;
                    if (path) openFileModal(path);
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
}

// === Запрос к /rag/agent/stream ===

async function sendServerQuery() {
    const question = questionInput.value.trim();
    if (!question) return;
    if (isGenerating) return;
    if (!inputsUnlocked) return;

    isGenerating = true;
    unlockInputs(false);

    appendMessage(question, true);
    questionInput.value = '';
    last_question = question;
    ensureConversation(question);

    const botMsg = appendMessage('', false, []);
    botMsg.addDots();

    let fullAnswer = '';
    let sourcesData = [];
    let gotAnswer = false;

    try {
        const response = await fetch('/rag/agent/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: question })
        });

        if (!response.ok) {
            let detail = "Ошибка сети";
            try {
                const err = await response.json();
                detail = err.error || err.detail || detail;
            } catch (e) { /* ignore */ }
            throw new Error(detail);
        }
        if (!response.body) throw new Error("Поток не поддерживается");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value);
            const chunks = buffer.split('\n');
            buffer = chunks.pop();

            for (const chunk of chunks) {
                const line = chunk.trim();
                if (!line.startsWith('data: ')) continue;
                let data;
                try {
                    data = JSON.parse(line.substring(6));
                } catch (e) {
                    console.warn("Не удалось распарсить строку данных:", line, e);
                    continue;
                }

                if (data.type === 'sources') {
                    sourcesData = data.data;
                } else if (data.type === 'token') {
                    if (fullAnswer === '') botMsg.removeDots();
                    fullAnswer += data.data;
                    botMsg.appendText(data.data);
                    const cc = document.getElementById('chat-container');
                    if (cc) cc.scrollTop = cc.scrollHeight;
                } else if (data.type === 'done') {
                    gotAnswer = true;
                    botMsg.showSources(data.sources || sourcesData);
                    await saveConversation(last_question, fullAnswer, data.sources || sourcesData);
                    isGenerating = false;
                    unlockInputs(true);
                } else if (data.type === 'error') {
                    botMsg.removeDots();
                    botMsg.updateText("Ошибка: " + data.data);
                    isGenerating = false;
                    unlockInputs(true);
                }
            }
        }

        if (buffer.trim()) {
            const line = buffer.trim();
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.substring(6));
                    if (data.type === 'token') {
                        if (fullAnswer === '') botMsg.removeDots();
                        fullAnswer += data.data;
                        botMsg.appendText(data.data);
                    } else if (data.type === 'done') {
                        gotAnswer = true;
                        botMsg.showSources(data.sources || sourcesData);
                        await saveConversation(last_question, fullAnswer, data.sources || sourcesData);
                    } else if (data.type === 'error') {
                        botMsg.removeDots();
                        botMsg.updateText("Ошибка: " + data.data);
                    }
                } catch (e) { /* ignore */ }
            }
        }

        if (!gotAnswer) {
            botMsg.removeDots();
            botMsg.updateText(fullAnswer || "Ответ пуст");
        }
    } catch (error) {
        botMsg.removeDots();
        botMsg.updateText("Ошибка соединения: " + error.message);
    } finally {
        isGenerating = false;
        unlockInputs(true);
    }
}

function sendQuery() {
    const text = questionInput.value.trim();
    if (!text) return;
    if (isGenerating || !inputsUnlocked) return;
    const low = text.toLowerCase();
    // Системные команды.
    if (low === '/help') {
        questionInput.value = '';
        showCommandsHelp();
        return;
    }
    if (low === '/new') {
        questionInput.value = '';
        startNewChat();
        return;
    }
    if (low === '/clear') {
        questionInput.value = '';
        const btn = document.getElementById('clearHistoryBtn');
        if (btn) btn.click();
        else location.reload();
        return;
    }
    // Команда создания служебной записки.
    if (low.startsWith('/create')) {
        questionInput.value = '';
        MemoWizard.start(text);
        return;
    }
    // Если мастер активен — передаём ввод процессу мастера.
    if (typeof MemoWizard !== 'undefined' && MemoWizard.isActive()) {
        questionInput.value = '';
        MemoWizard.handleInput(text);
        return;
    }
    // Простой запрос: показываем полный список служебных записок.
    showAllMemos();
}

// Простой запрос (не команда и не мастер) выводит все служебные записки
// из базы вместе с их содержимым — без обращения к LLM.
async function showAllMemos() {
    const question = questionInput.value.trim();
    if (!question) return;
    if (isGenerating) return;
    if (!inputsUnlocked) return;

    isGenerating = true;
    unlockInputs(false);

    appendMessage(question, true);
    questionInput.value = '';
    last_question = question;
    ensureConversation(question);

    const botMsg = appendMessage('', false, []);
    botMsg.addDots();

    try {
        const response = await fetch('/api/memos?q=' + encodeURIComponent(question));
        if (!response.ok) throw new Error("HTTP " + response.status);
        const data = await response.json();
        const memos = Array.isArray(data.memos) ? data.memos : [];
        botMsg.removeDots();
        if (!memos.length) {
            botMsg.updateText('По запросу "' + question + '" служебные записки не найдены. Попробуйте уточнить тему.');
            await saveConversation(last_question, 'По запросу "' + question + '" служебные записки не найдены.', []);
            return;
        }
        botMsg.content.innerHTML = memoListHtml(memos, question);
        await saveConversation(
            last_question,
            'Найдено служебных записок: ' + memos.length + ' шт. по запросу "' + question + '"',
            memos.map(m => ({ file_name: m.file_name, file_path: m.file_path, score: null })),
            { memoList: memos }
        );
    } catch (e) {
        botMsg.removeDots();
        botMsg.updateText('Ошибка получения служебных записок: ' + e.message);
    } finally {
        isGenerating = false;
        unlockInputs(true);
    }
}

// Рендер HTML-списка служебных записок (используется при выводе и при
// восстановлении диалога после обновления страницы).
function memoListHtml(memos, questionLabel) {
    const memosArr = Array.isArray(memos) ? memos : [];
    const items = memosArr.map(m => {
        const title = (m.file_name || '').replace(/\.docx$/i, '');
        const body = (m.text || '').trim();
        const path = m.file_path || '';
        return '<li>' + escapeHtml(title) +
            '<div class="memo-meta"><span class="memo-path">' + escapeHtml(path) + '</span>' +
            '<button type="button" class="btn btn-sm btn-outline-secondary memo-copy" data-path="' + escapeHtml(path) + '" title="Скопировать путь к файлу">Скопировать путь</button>' +
            '<button type="button" class="btn btn-sm btn-outline-primary memo-fav" data-title="' + escapeHtml(title) + '" data-path="' + escapeHtml(path) + '" title="Сохранить служебную записку в избранное">Сохранить в избранное</button></div>' +
            '<div class="memo-list-body">' + escapeHtml(body) + '</div></li>';
    }).join('\n');
    return '<div class="memo-list"><h6><b>Служебные записки по запросу "' + (questionLabel || '') + '" (' + memosArr.length + '):</b></h6><ol>' + items + '</ol></div>';
}

// Сохранение отдельной служебной записки в избранное (без диалога).
async function saveMemoToFavorites(btn) {
    const title = btn.dataset.title || '';
    const path = btn.dataset.path || '';
    const memo = btn.closest('li')?.querySelector('.memo-list-body')?.textContent || '';
    const question = 'Служебная записка: ' + title;
    await saveAnswerToFavorites(question, memo || question, [
        { file_name: title + '.docx', file_path: path, score: null }
    ]);
    const old = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-bookmark-check-fill"></i> В избранном';
    btn.classList.add('btn-success');
    btn.classList.remove('btn-outline-primary');
    setTimeout(() => { btn.innerHTML = old; btn.classList.remove('btn-success'); btn.classList.add('btn-outline-primary'); }, 2000);
}

async function copyMemoPath(btn) {
    const path = btn.dataset.path || '';
    try {
        await navigator.clipboard.writeText(path);
        const old = btn.textContent;
        btn.textContent = 'Скопировано';
        setTimeout(() => { btn.textContent = old; }, 1200);
    } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = path;
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand('copy');
            const old = btn.textContent;
            btn.textContent = 'Скопировано';
            setTimeout(() => { btn.textContent = old; }, 1200);
        } catch (e2) {
            btn.textContent = 'Ошибка';
            setTimeout(() => { btn.textContent = 'Скопировать путь'; }, 1200);
        }
        document.body.removeChild(ta);
    }
}

// === Команды чата (подсказка при вводе "/") ===

const CHAT_COMMANDS = [
    { cmd: '/create', desc: 'Служебная записка по теме: /create тема' },
    { cmd: '/new', desc: 'Начать новый диалог' },
    { cmd: '/clear', desc: 'Очистить всю историю диалогов и ответов' },
    { cmd: '/help', desc: 'Показать список команд' },
];

function showCommandMenu(filter) {
    const wrap = document.getElementById('command-menu-wrap');
    if (!wrap) return;
    const menu = document.getElementById('command-menu');
    const query = (filter || '').toLowerCase();
    const items = query ? CHAT_COMMANDS.filter(c => c.cmd.toLowerCase().startsWith(query)) : CHAT_COMMANDS;
    if (!items.length) {
        wrap.classList.add('d-none');
        return;
    }
    menu.innerHTML = items.map(c =>
        `<div class="command-menu-item" data-cmd="${c.cmd}">
            <span class="cmd-name">${c.cmd}</span>
            <span class="cmd-desc">${c.desc}</span>
        </div>`).join('');
    wrap.classList.remove('d-none');
    menu.querySelectorAll('.command-menu-item').forEach(el => {
        el.addEventListener('click', () => pickCommand(el.dataset.cmd));
        el.addEventListener('mousedown', (e) => e.preventDefault());
    });
}

function hideCommandMenu() {
    const wrap = document.getElementById('command-menu-wrap');
    if (wrap) wrap.classList.add('d-none');
}

function pickCommand(cmd) {
    hideCommandMenu();
    if (cmd === '/create') {
        questionInput.value = '/create ';
        questionInput.focus();
        return;
    }
    questionInput.value = '';
    if (cmd === '/new') {
        startNewChat();
    } else if (cmd === '/clear') {
        const btn = document.getElementById('clearHistoryBtn');
        if (btn) btn.click();
    } else if (cmd === '/help') {
        showCommandsHelp();
    }
}

function showCommandsHelp() {
    const lines = ['**Команды чата:**'];
    CHAT_COMMANDS.forEach(c => {
        lines.push(`- \`${c.cmd}\` — ${c.desc}`);
    });
    appendMessage(lines.join('\n'), false);
}

// === История на сервере ===

// Создаёт/гарантирует диалог в истории сразу при первом сообщении (до ответа).
// Каждое следующее сообщение без активного диалога открывает новый.
async function ensureConversation(question) {
    if (activeConversationId) return;
    const conversation = {
        id: generateUUID(),
        question: question,
        messages: [
            { role: 'user', text: question },
        ],
        previewText: question.substring(0, 150),
        lastAnswer: '',
        sources: [],
        date: Date.now(),
        lastAccessed: Date.now()
    };
    activeConversationId = conversation.id;
    try {
        await fetch('/api/conversations', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(conversation)
        });
    } catch (e) {
        console.error("Ошибка сохранения диалога:", e);
    }
    loadServerHistory();
}

async function saveConversation(question, answer, sources, options = {}) {
    const botMsgData = { role: 'bot', text: answer, sources: sources };
    if (Array.isArray(options.memoList)) botMsgData.memoList = options.memoList;
    const conversation = {
        id: activeConversationId || generateUUID(),
        question: question,
        messages: [
            { role: 'user', text: question },
            botMsgData
        ],
        previewText: answer.substring(0, 150),
        lastAnswer: answer,
        sources: sources,
        date: Date.now(),
        lastAccessed: Date.now()
    };
    activeConversationId = conversation.id;
    try {
        await fetch('/api/conversations', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(conversation)
        });
    } catch (e) {
        console.error("Ошибка сохранения диалога:", e);
    }
    loadServerHistory();
}

async function loadServerHistory() {
    try {
        const resp = await fetch('/api/history');
        const data = await resp.json();
        renderHistory(data.conversations || [], data.answers || []);
    } catch (e) {
        console.error("Ошибка загрузки истории:", e);
    }
}

async function deleteConversationFromServer(convId) {
    try {
        await fetch('/api/conversations/' + encodeURIComponent(convId), { method: 'DELETE' });
    } catch (e) {
        console.error("Ошибка удаления диалога:", e);
    }
    loadServerHistory();
}

async function deleteAnswerFromServer(ansId) {
    try {
        await fetch('/api/answers/' + encodeURIComponent(ansId), { method: 'DELETE' });
    } catch (e) {
        console.error("Ошибка удаления ответа:", e);
    }
    loadServerHistory();
}

async function renameConversationOnServer(convId, newName) {
    const conv = (await (await fetch('/api/history')).json()).conversations.find(c => c.id === convId);
    if (conv) {
        conv.question = newName;
        try {
            await fetch('/api/conversations', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(conv)
            });
        } catch (e) { console.error("Ошибка переименования диалога:", e); }
    }
    loadServerHistory();
}

async function renameAnswerOnServer(ansId, newName) {
    const ans = (await (await fetch('/api/history')).json()).answers.find(a => a.id === ansId);
    if (ans) {
        ans.question = newName;
        try {
            await fetch('/api/answers', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(ans)
            });
        } catch (e) { console.error("Ошибка переименования ответа:", e); }
    }
    loadServerHistory();
}

function renderHistory(conversations, answers) {
    const conversationsTab = document.getElementById('conversationsTab');
    const answersTab = document.getElementById('answersTab');
    conversationsTab.innerHTML = '';
    answersTab.innerHTML = '';

    if (conversations.length === 0) {
        conversationsTab.innerHTML = `
            <div class="empty-history">
                <div class="empty-icon">💬</div>
                <p>У вас пока нет сохраненных чатов</p>
                <small class="text-muted">Начните диалог, чтобы сохранить его в историю</small>
            </div>`;
    } else {
        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (conv.id === activeConversationId) item.classList.add('active');

            const title = conv.question || conv.messages?.[0]?.text || 'Без названия';
            const dateStr = new Date(conv.date).toLocaleDateString('ru-RU');

            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div class="conv-question text-truncate flex-grow-1" title="${escapeHtml(title)}">
                        ${escapeHtml(title)}
                    </div>
                    <div class="btn-group ms-2 flex-nowrap">
                        <button class="btn btn-sm btn-link p-0 edit-chat-btn" data-id="${conv.id}" title="Переименовать">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-link text-danger p-0 delete-chat-btn" data-id="${conv.id}" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="conv-meta small text-muted d-flex justify-content-between">
                    <span>${dateStr}</span>
                    <span class="conv-time-ago">${formatTimeAgo(conv.lastAccessed || conv.date)}</span>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.closest('.btn-group') || e.target.tagName === 'INPUT') return;
                loadConversation(conv.id);
            });

            item.querySelector('.edit-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                startRename(item, conv.id, title, (newName) => renameConversationOnServer(conv.id, newName));
            });

            item.querySelector('.delete-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Удалить диалог "${title}"?`)) {
                    if (conv.id === activeConversationId) {
                        activeConversationId = null;
                        document.getElementById('chat-container').innerHTML = '';
                    }
                    deleteConversationFromServer(conv.id);
                }
            });

            conversationsTab.appendChild(item);
        });
    }

    if (answers.length === 0) {
        answersTab.innerHTML = `
            <div class="empty-history">
                <div class="empty-icon">💡</div>
                <p>У вас пока нет избранных ответов</p>
                <small class="text-muted">Отмечайте важные ответы, чтобы сохранить их здесь</small>
            </div>`;
    } else {
        answers.forEach(ans => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (ans.id === activeAnswerId) item.classList.add('active');
            const cleanTitle = ans.question || 'Без названия';

            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div class="conv-question text-truncate flex-grow-1" title="${escapeHtml(cleanTitle)}">
                        ${escapeHtml(cleanTitle)}
                    </div>
                    <div class="btn-group ms-2 flex-nowrap">
                        <button class="btn btn-sm btn-link p-0 edit-chat-btn" data-id="${ans.id}" title="Переименовать">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-link text-danger p-0 delete-chat-btn" data-id="${ans.id}" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="conv-meta text-muted small d-flex justify-content-between">
                    <span>${new Date(ans.date).toLocaleDateString()}</span>
                    <span class="conv-time-ago">${formatTimeAgo(ans.lastAccessed || ans.date)}</span>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.closest('.btn-group') || e.target.tagName === 'INPUT') return;
                loadAnswer(ans.id);
            });

            item.querySelector('.edit-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                startRename(item, ans.id, cleanTitle, (newName) => renameAnswerOnServer(ans.id, newName));
            });

            item.querySelector('.delete-chat-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Удалить ответ "${cleanTitle}"?`)) {
                    deleteAnswerFromServer(ans.id);
                }
            });

            answersTab.appendChild(item);
        });
    }
}

function startRename(itemEl, id, currentTitle, onUpdate) {
    const titleDiv = itemEl.querySelector('.conv-question');
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
        loadServerHistory();
    };
    input.addEventListener('blur', save);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') input.blur();
        if (e.key === 'Escape') input.remove();
    });
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('conversationsTab').style.display = tabName === 'conversations' ? 'block' : 'none';
    document.getElementById('answersTab').style.display = tabName === 'answers' ? 'block' : 'none';
}

function loadConversation(convId) {
    fetch('/api/history').then(r => r.json()).then(data => {
        const conv = data.conversations.find(c => c.id === convId);
        if (!conv) return;
        activeConversationId = convId;
        last_question = conv.question || conv.messages?.[0]?.text || '';
        const chatContainer = document.getElementById('chat-container');
        if (chatContainer) chatContainer.innerHTML = '';

        const messages = conv.messages || [
            { role: 'user', text: conv.question },
            { role: 'bot', text: conv.lastAnswer, sources: conv.sources }
        ];

        messages.forEach(msg => {
            const msgObj = appendMessage(msg.text, msg.role === 'user', []);
            if (msg.role === 'bot' && Array.isArray(msg.memoList) && msg.memoList.length) {
                const questionLabel = msg.question || conv.question || '';
                const html = memoListHtml(msg.memoList, questionLabel);
                msgObj.content.innerHTML = html;
            } else if (msg.role === 'bot' && msg.sources && msg.sources.length > 0) {
                msgObj.showSources(msg.sources);
            }
        });

        if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
        renderHistory(data.conversations, data.answers);
        isGenerating = false;
        unlockInputs(true);
    }).catch(console.error);
}

function loadAnswer(ansId) {
    fetch('/api/history').then(r => r.json()).then(data => {
        const ans = data.answers.find(a => a.id === ansId);
        if (!ans) return;
        activeConversationId = null;
        last_question = ans.question || '';
        const chatContainer = document.getElementById('chat-container');
        if (chatContainer) chatContainer.innerHTML = '';

        appendMessage(`[Избранное] Вопрос: ${ans.question}`, true);
        const botMsg = appendMessage(ans.answer || ans.previewText || '', false);
        if (ans.sources && ans.sources.length > 0) {
            botMsg.showSources(ans.sources);
        }
        renderHistory(data.conversations, data.answers);
    }).catch(console.error);
}

async function saveAnswerToFavorites(question, answer, sources) {
    const ansId = generateUUID();
    try {
        await fetch('/api/answers', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: ansId,
                question: question,
                answer: answer,
                previewText: answer.substring(0, 150),
                sources: sources,
                date: Date.now(),
                lastAccessed: Date.now()
            })
        });
    } catch (e) {
        console.error("Ошибка сохранения в избранное:", e);
    }
    loadServerHistory();

    const notification = document.createElement('div');
    notification.className = 'alert alert-success position-fixed bottom-0 end-0 m-3';
    notification.style.zIndex = '2100';
    notification.innerHTML = `<i class="bi bi-bookmark-check-fill me-2"></i>Ответ сохранен в избранное`;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3000);
}

function startNewChat() {
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer) chatContainer.innerHTML = '';
    activeConversationId = null;
    last_question = "";
    if (questionInput) questionInput.value = "";
    appendMessage("🔄 Новый диалог начат. Вы можете задать вопрос.", false);
}

// === Синхронизация (Overlay) ===

function showSyncOverlay() {
    document.getElementById('sync-overlay').classList.add('active');
    unlockInputs(false);
    systemStatus.textContent = "Синхронизация...";
    systemStatus.className = "text-primary fw-bold";
}

function hideSyncOverlay(isReady = true) {
    document.getElementById('sync-overlay').classList.remove('active');
    if (isReady) {
        systemStatus.textContent = "Готов к работе";
        systemStatus.className = "text-success fw-bold";
    } else {
        systemStatus.textContent = "Ошибка инициализации";
        systemStatus.className = "text-danger fw-bold";
    }
    unlockInputs(true);
}

let wasSyncing = false;

async function checkSyncStatus() {
    try {
        const response = await fetch('/rag/index/status');
        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }
        const data = await response.json();

        if (data.is_syncing || !data.initialized) {
            if (!document.getElementById('sync-overlay').classList.contains('active')) {
                showSyncOverlay();
            }
            document.getElementById('sync-status-text').textContent = data.status;
            const html = data.sync_files
                ? data.sync_files.map(item => `${item.file} (${item.operation})`).join('<br>')
                : 'Нет информации о файлах';
            document.getElementById('sync-file-text').innerHTML = html;
            const progress = Number(data.progress) || 0;
            document.getElementById('sync-progress-bar').style.width = `${progress}%`;
            document.getElementById('sync-percent-text').textContent = `${progress}%`;
        } else {
            if (document.getElementById('sync-overlay').classList.contains('active')) {
                hideSyncOverlay(true);
                if (wasSyncing) {
                    setTimeout(() => {
                        appendMessage("✅ База знаний загружена и готова к работе!", false);
                    }, 500);
                    wasSyncing = false;
                }
            }
            if (data.initialized && !inputsUnlocked && !isGenerating) {
                unlockInputs(true);
                systemStatus.textContent = "Готов к работе";
                systemStatus.className = "text-success fw-bold";
            }
        }
    } catch (e) {
        console.error("Ошибка проверки статуса:", e);
        systemStatus.textContent = "Ошибка соединения";
        systemStatus.className = "text-danger fw-bold";
        unlockInputs(true);
    }
}

// === Модальное окно файла ===

function openFileModal(filePath) {
    document.getElementById('filePath').value = filePath;
    const modal = new bootstrap.Modal(document.getElementById('fileModal'));
    modal.show();
    parseFile(filePath);
}

async function parseFile(filePath) {
    const spinner = document.getElementById('spinner');
    const resultContent = document.getElementById('result-content');
    const errorMsg = document.getElementById('error-message');

    errorMsg.style.display = 'none';
    resultContent.innerHTML = '';
    spinner.style.display = 'block';

    try {
        const response = await fetch('/rag/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath })
        });
        const data = await response.json();
        if (response.ok && data.ok) {
            resultContent.innerHTML = marked.parse(data.content);
        } else {
            showError(data.error || 'Произошла ошибка при обработке');
        }
    } catch (err) {
        showError('Ошибка сети: ' + err.message);
    } finally {
        spinner.style.display = 'none';
    }
}

function showError(message) {
    const errorMsg = document.getElementById('error-message');
    errorMsg.textContent = message;
    errorMsg.style.display = 'block';
    errorMsg.scrollIntoView({ behavior: 'smooth' });
}

function copyFilePath() {
    const filePath = document.getElementById('filePath').value;
    navigator.clipboard.writeText(filePath).then(() => {
        const button = document.getElementById('copyButton');
        const originalIcon = button.innerHTML;
        button.innerHTML = '<i class="bi bi-check"></i>';
        setTimeout(() => { button.innerHTML = originalIcon; }, 2000);
    }).catch(console.error);
}

// === Инициализация ===

document.addEventListener('DOMContentLoaded', () => {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(tooltipTriggerEl => {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    document.getElementById('send-btn').addEventListener('click', sendQuery);
    questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const wrap = document.getElementById('command-menu-wrap');
            if (wrap && !wrap.classList.contains('d-none')) {
                e.preventDefault();
                const first = wrap.querySelector('.command-menu-item');
                if (first) {
                    first.click();
                    return;
                }
            }
            sendQuery();
        }
    });

    // Подсказка команд при вводе "/".
    questionInput.addEventListener('input', () => {
        const v = questionInput.value.trim();
        if (v.startsWith('/') && !v.includes(' ')) {
            showCommandMenu(v);
        } else {
            hideCommandMenu();
        }
    });
    questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') hideCommandMenu();
        if (e.key === 'Backspace') {
            const v = questionInput.value.trim();
            if (v.length <= 1) hideCommandMenu();
        }
    });
    document.addEventListener('click', (e) => {
        const wrap = document.getElementById('command-menu-wrap');
        if (wrap && !wrap.contains(e.target) && e.target.id !== 'question-input') {
            hideCommandMenu();
        }
        const copyBtn = e.target.closest('.memo-copy');
        if (copyBtn) copyMemoPath(copyBtn);
        const favBtn = e.target.closest('.memo-fav');
        if (favBtn) saveMemoToFavorites(favBtn);
    });

    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', async () => {
            if (confirm('Очистить всю историю диалогов и избранных ответов?')) {
                try {
                    await fetch('/api/history/clear', { method: 'POST' });
                } catch (e) { console.error(e); }
                loadServerHistory();
            }
        });
    }

    loadServerHistory();

    // Восстанавливаем незавершённый мастер служебной записки (через localStorage),
    // а если его нет — открываем последний диалог.
    setTimeout(() => {
        if (typeof MemoWizard !== 'undefined' && typeof MemoWizard.restoreSession === 'function') {
            MemoWizard.restoreSession().then(restored => {
                if (!restored) loadLastConversation();
            });
        } else {
            loadLastConversation();
        }
    }, 300);

    setInterval(checkSyncStatus, 500);
    checkSyncStatus();
});

function loadLastConversation() {
    fetch('/api/history').then(r => r.json()).then(data => {
        const convs = data.conversations || [];
        if (!convs.length) return;
        let last = convs[0];
        convs.forEach(c => {
            const t = c.lastAccessed || c.date || 0;
            if (t > (last.lastAccessed || last.date || 0)) last = c;
        });
        loadConversation(last.id);
    }).catch(() => {});
}