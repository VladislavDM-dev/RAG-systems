// === Мастер генерации служебной записки (/create) ===

const MemoWizard = {
    step: null,          // 'topic' | 'fields' | 'check'
    topic: '',
    fields: {},
    variants: [],        // [{text, sources}]
    chosen: null,        // индекс выбранного варианта
    botMsg: null,        // текущее сообщение бота в чате
    fieldOptions: {},    // варианты значений полей из RAG
    fieldDefsNoBody: [],
    keys: [],
    resultBtns: null,

// === Сессия (хранится на сервере, без localStorage) ===
    async saveState() {
        try {
            const st = {
                ts: Date.now(),
                step: this.step,
                topic: this.topic,
                variants: (this.variants || []).map(v => ({ text: v.text, sources: v.sources || [], idx: v.idx })),
                chosen: this.chosen,
                fieldOptions: this.fieldOptions,
                fields: this.fields,
                fieldDefsNoBody: this.fieldDefsNoBody || [],
                keys: this.keys || [],
            };
            await fetch('/api/memo/state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: st }),
            });
        } catch (e) { /* сервер недоступен — состояние не сохранится */ }
    },

    clearState() {
        try { fetch('/api/memo/state', { method: 'DELETE' }); } catch (e) { /* ignore */ }
    },

    async restoreSession() {
        let st = null;
        try {
            const res = await fetch('/api/memo/state');
            const data = await res.json().catch(() => ({}));
            st = data && data.state ? data.state : null;
        } catch (e) { st = null; }
        if (!st || !st.topic) return false;

        this.step = st.step;
        this.topic = st.topic;
        this.variants = st.variants || [];
        this.chosen = st.chosen;
        this.fieldOptions = st.fieldOptions || {};
        this.fields = st.fields || {};
        this.fieldDefsNoBody = st.fieldDefsNoBody || [];
        this.keys = st.keys || [];

        this.botMsg = Chat.appendMessage('', false, [], 'memo-wide');

        if (this.step === 'fields') {
            const body = this.fields.body || (
                this.chosen != null && this.variants[this.chosen]
                    ? this.variants[this.chosen].text
                    : this.topic);
            this.renderFields(this.fieldDefsNoBody, this.fields, [body], true, true);
            this.sendBot('↩️ Сессия восстановлена: выберите вариант текста, исправьте поля и нажмите «Далее».');
            return true;
        }
        if (this.step === 'check') {
            this.resultBtns = null;
            await this.showResult();
            this.sendBot('↩️ Сессия восстановлена: черновик готов к печати или редактированию.');
            return true;
        }
        this.clearState();
        return false;
    },

    reset() {
        this.step = null;
        this.topic = '';
        this.fields = {};
        this.variants = [];
        this.chosen = null;
        this.botMsg = null;
        this.fieldOptions = {};
        this.fieldDefsNoBody = [];
        this.keys = [];
        this.resultBtns = null;
        this.clearState();
    },

    isActive() {
        return this.step === 'topic' || this.step === 'fields' || this.step === 'check';
    },

    async start(inputText) {
        if (Chat.isGenerating || !Chat.inputsUnlocked) return;
        this.reset();
        let topic = '';
        if (inputText && inputText.trim()) {
            let parts = inputText.split(/\s+/);
            if (parts[0].toLowerCase() === '/create') parts.shift();
            topic = parts.join(' ').trim();
        }
        if (topic) {
            this.topic = topic;
            await this.offerVariants();
        } else {
            this.step = 'topic';
            await this.sendBot('Команда создания служебной записки. \nУкажите **тему** служебной записки.');
        }
    },

    async handleInput(text) {
        if (!text || Chat.isGenerating) return;
        if (this.step === 'topic') {
            this.topic = text;
            await this.offerVariants();
        } else if (this.step === 'fields') {
            this.sendBot('Заполните поля выше и нажмите «Далее».');
        } else if (this.step === 'check') {
            this.sendBot('Нажмите кнопку «Скачать .docx и сохранить» ниже.');
        }
    },

async offerVariants() {
        this.step = 'fields';
        this.botMsg = Chat.appendMessage('', false, [], 'memo-wide');
        this.botMsg.addDots();
        this.botMsg.updateText('Генерирую **варианты служебной записки** по теме и подбираю значения полей из базы знаний...');
        Chat.isGenerating = true;
        Chat.unlockInputs(false);

        try {
            const f = await fetch('/api/memo/template');
            const data = await f.json().catch(() => ({ fields: [] }));
            const fieldDefs = Array.isArray(data.fields) && data.fields.length
                ? data.fields
                : [{ key: 'recipient_position', label: 'Кому (должность)', hint: '' },
                   { key: 'recipient_name', label: 'Кому (ФИО)', hint: '' },
                   { key: 'memo_number', label: 'Номер служебной записки', hint: '' },
                   { key: 'date', label: 'Дата', hint: '' },
                   { key: 'sender_position', label: 'Подписывающее лицо (должность)', hint: '' },
                   { key: 'sender_short_name', label: 'Подписывающее лицо (ФИО, кратко)', hint: '' }];
            this.fieldDefsNoBody = fieldDefs.filter(d => d.key !== 'body');
            this.fieldDefsNoBody.forEach(d => {
                if (d.key === 'sender_position') d.label = 'Подписывающее лицо (должность)';
                else if (d.key === 'sender_short_name') d.label = 'Подписывающее лицо (ФИО, кратко)';
            });
            this.keys = this.fieldDefsNoBody.map(d => d.key);

            const variants = await this.generateVariants();
            this.variants = variants.map((v, i) => ({ ...v, idx: i }));
            this.chosen = 0;

            let fieldOptions = {};
            try {
                fieldOptions = await this.generateFieldOptions(this.keys);
            } catch (e) { /* поля останутся пустыми */ }
            this.fieldOptions = fieldOptions;

            const body = this.variants.length ? this.variants[0].text : '';
            if (!body) {
                this.botMsg.updateText('Не удалось получить варианты текста по теме «' + this.topic + '». Уточните тему или переформулируйте запрос.');
                Chat.isGenerating = false;
                Chat.unlockInputs(true);
                return;
            }
            this.renderFields(this.fieldDefsNoBody, {}, [body], true, true);
        } catch (e) {
            this.botMsg.updateText('Ошибка генерации: ' + e.message);
        } finally {
            Chat.isGenerating = false;
            Chat.unlockInputs(true);
        }
    },

    async generateVariants() {
        let res;
        try {
            res = await streamAgentRequest({
                prompt: 'Служебная записка по теме: ' + this.topic + '. Подготовь несколько вариантов текста.',
                system_prompt: MEMO_VARIANTS_SYSTEM_PROMPT,
                temperature: 0.7,
            });
        } catch (e) {
            return [];
        }
        if (!res.answer) return [];
        const raw = parseMemoJson(res.answer);
        const variants = extractMemoVariants(raw);
        const src = Array.isArray(res.sources) && res.sources.length
            ? res.sources
            : (Array.isArray(raw && raw.sources) ? raw.sources : []);
        if (!variants.length) {
            const text = String(res.answer).trim();
            if (text) return [{ text, sources: src }];
            return [];
        }
        variants.forEach(v => { if (!v.sources || !v.sources.length) v.sources = src; });
        return variants;
    },

    renderFields(fieldDefsNoBody, prefill, bodies, includeBody, showBodyPick) {
        const fieldOptions = this.fieldOptions || {};
        let variantsHtml = '';
        if (showBodyPick && this.variants && this.variants.length) {
            variantsHtml = '<div class="mb-2">' +
                '<em>Выберите вариант текста записки (из RAG) или отредактируйте его:</em>' +
                '<div class="d-flex flex-wrap gap-1 mt-1 memo-variant-picks">' +
                this.variants.map((v, vi) =>
                    '<button type="button" class="btn btn-sm btn-outline-primary memo-body-pick' + (vi === (this.chosen || 0) ? ' btn-primary' : '') + '" data-idx="' + vi + '">Вариант ' + (vi + 1) + '</button>'
                ).join('') + '</div></div>';
        }
        let html = '<div class="memo-fields">' +
            '<h6>Служебная записка по теме: <em>' + escapeHtml(this.topic) + '</em></h6>' +
            variantsHtml;
        if (includeBody || showBodyPick) {
            html += '<label class="form-label small mb-0 mt-1">Текст служебной записки:</label>' +
                '<textarea class="form-control form-control-sm memo-edit-body" id="memo-edit-body" rows="10" style="white-space:pre-wrap">' + escapeHtml(bodies[0] || '') + '</textarea>';
        }
        html += '<em>Поля «Дата» и «Номер» заполняются вручную, остальные — вариантом из RAG или своим значением:</em>' +
            '<div class="mb-2 mt-2">';
        fieldDefsNoBody.forEach(def => {
            const key = def.key;
            const label = def.label || key;
            const hint = def.hint || '';
            const manualOnly = key === 'date' || key === 'memo_number';
            const isDate = key === 'date';
            const opts = (fieldOptions[key] || []).filter(v => v && String(v).trim());
            let cur = prefill[key] || '';
            if (isDate && !cur) {
                const now = new Date();
                const dd = String(now.getDate()).padStart(2, '0');
                const mm = String(now.getMonth() + 1).padStart(2, '0');
                cur = dd + '.' + mm + '.' + now.getFullYear();
                this.fields[key] = cur;
            }
            let optionsHtml = '';
            const optionButtons = [];
            if (!manualOnly && opts.length) {
                opts.forEach((opt, oi) => {
                    const selected = cur === String(opt).trim() ? ' btn-primary' : '';
                    optionButtons.push(
                        '<button type="button" class="btn btn-sm btn-outline-secondary memo-option' + selected + '" data-key="' + key + '" data-oi="' + oi + '" data-value="' + escapeHtml(opt) + '">' + escapeHtml(opt) + '</button>'
                    );
                });
                optionsHtml = '<div class="d-flex flex-wrap gap-1 mb-1 memo-options" data-key="' + key + '">' +
                    optionButtons.join('') + '</div>';
            }
            const inputVal = isDate ? toDateInputValue(cur) : cur;
            const hasChosen = optionButtons.length && cur && (prefill[key] || '').trim() &&
                opts.some(o => String(o).trim() === String(prefill[key]).trim());
            const inputVisible = manualOnly || !hasChosen;
            html += '<div class="memo-field mb-2">' +
                '<div class="d-flex align-items-center gap-2">' +
                '<label class="form-label small mb-0">' + escapeHtml(label) + '</label>' +
                (manualOnly ? '' : '<button type="button" class="btn btn-link btn-sm p-0 memo-custom-toggle" data-key="' + key + '">ввести своё</button>') +
                '</div>' +
                optionsHtml +
                '<input type="' + (isDate ? 'date' : 'text') + '" class="form-control form-control-sm memo-input ' + (inputVisible ? '' : 'd-none') + '" data-key="' + key + '" value="' + escapeHtml(inputVal) + '"' +
                (isDate ? '' : (hint ? ' placeholder="' + escapeHtml(hint) + '"' : '')) + ' placeholder="' + (manualOnly && !isDate ? 'Заполните вручную' : 'Свой вариант') + '">' +
                '</div>';
        });
        html += '</div>' +
            '<div class="d-flex gap-2 flex-wrap">' +
            '<button class="btn btn-sm btn-primary" id="memo-choice-next">Далее</button>' +
            '<button class="btn btn-sm btn-outline-secondary" id="memo-choice-random">Предложить поля из RAG заново</button>' +
            '</div>' +
            '<div id="memo-choice-status" class="small text-muted mt-2"></div></div>';

        this.botMsg.updateText('');
        this.botMsg.content.innerHTML = html;
        this.botMsg.removeDots();

        const self = this;

        if (showBodyPick && this.variants && this.variants.length) {
            this.botMsg.content.querySelectorAll('.memo-body-pick').forEach(btn => {
                btn.addEventListener('click', () => {
                    const idx = parseInt(btn.dataset.idx, 10);
                    const body = self.variants[idx] ? self.variants[idx].text : '';
                    const ta = document.getElementById('memo-edit-body');
                    if (ta) ta.value = body;
                    self.chosen = idx;
                    self.fields.body = body;
                    self.botMsg.content.querySelectorAll('.memo-body-pick').forEach(b =>
                        b.classList.toggle('btn-primary', b === btn));
                    self.saveState();
                });
            });
        }

        const linkedPairs = {
            recipient_position: 'recipient_name',
            recipient_name: 'recipient_position',
            sender_position: 'sender_short_name',
            sender_short_name: 'sender_position',
            executor: 'phone',
            phone: 'executor',
        };
        const selectOption = (btn) => {
            const key = btn.dataset.key;
            const input = self.botMsg.content.querySelector('input[data-key="' + key + '"]');
            if (input) { input.value = ''; input.classList.add('d-none'); }
            self.botMsg.content.querySelectorAll('.memo-option[data-key="' + key + '"]')
                .forEach(b => b.classList.remove('btn-primary'));
            btn.classList.add('btn-primary');
            self.fields[key] = btn.dataset.value;
            const linkedKey = linkedPairs[key];
            if (linkedKey) {
                const oi = btn.dataset.oi;
                const linked = self.botMsg.content.querySelector('.memo-option[data-key="' + linkedKey + '"][data-oi="' + oi + '"]');
                if (linked && !linked.classList.contains('btn-primary')) selectOption(linked);
                else if (linked) self.fields[linkedKey] = linked.dataset.value;
            }
            self.saveState();
        };

        this.botMsg.content.querySelectorAll('.memo-option').forEach(btn => {
            btn.addEventListener('click', () => selectOption(btn));
        });
        this.botMsg.content.querySelectorAll('.memo-custom-toggle').forEach(toggle => {
            toggle.addEventListener('click', () => {
                const key = toggle.dataset.key;
                const input = self.botMsg.content.querySelector('input[data-key="' + key + '"]');
                if (input) {
                    input.classList.toggle('d-none');
                    if (!input.classList.contains('d-none')) input.focus();
                }
                self.botMsg.content.querySelectorAll('.memo-option[data-key="' + key + '"]')
                    .forEach(b => b.classList.remove('btn-primary'));
                self.fields[key] = '';
                self.saveState();
            });
        });
        this.botMsg.content.querySelectorAll('.memo-input').forEach(input => {
            input.addEventListener('input', () => {
                self.fields[input.dataset.key] = input.value;
                self.saveState();
            });
        });
        const bodyTa = document.getElementById('memo-edit-body');
        if (bodyTa) {
            bodyTa.addEventListener('input', () => {
                self.fields.body = bodyTa.value;
                self.saveState();
            });
            this.fields.body = bodyTa.value;
            this.saveState();
        }

        const fillRandom = async () => {
            const status = document.getElementById('memo-choice-status');
            status.textContent = 'Подбираю поля из RAG...';
            try {
                const vals = await this.generateFieldOptions(this.keys);
                Object.keys(vals).forEach(k => {
                    if (k === 'date' || k === 'memo_number') return;
                    const input = self.botMsg.content.querySelector('input[data-key="' + k + '"]');
                    if (input && vals[k] && vals[k].length) input.value = vals[k][0];
                    const opt = self.botMsg.content.querySelector('.memo-option[data-key="' + k + '"]');
                    if (opt) selectOption(opt);
                });
                status.textContent = 'Поля обновлены. Проверьте и нажмите «Далее».';
            } catch (e) {
                status.textContent = 'Не удалось подобрать: ' + e.message;
            }
        };

        document.getElementById('memo-choice-next').addEventListener('click', () => this.collectFields());
        document.getElementById('memo-choice-random').addEventListener('click', fillRandom);
    },

    editDraft() {
        const f = this.fields || {};
        const body = this.chosen != null && this.variants[this.chosen]
            ? this.variants[this.chosen].text
            : this.topic;
        if (this.resultBtns) this.resultBtns.classList.add('d-none');
        this.step = 'fields';
        this.renderFields(this.fieldDefsNoBody || [], f, [body], true);
    },

    async generateFieldOptions(keys) {
        const schemaLines = JSON.stringify(
            Object.fromEntries(keys.map(k => [k, ['вариант1', 'вариант2']])),
            null, 2);
        const payload = {
            prompt: 'Служебная записка: ' + this.topic + '. Подготовь данные для её шапки.',
            system_prompt: 'Ты — помощник, который подбирает данные для шаблонов деловых документов. Верни ОДИН JSON-объект вида {"ключ": ["вариант1", "вариант2", ...]...} для ВСЕХ ключей из схемы, по 5-6 вариантов на каждый ключ. Значения бери из контекста, а если в контексте нет данных для ключа — придумай реалистичные значения. Для "executor" давай ТОЛЬКО Фамилию и инициалы вида "Иванов И.И.". Для "phone" — номера вида "+7 (900) 123-45-67". НЕ возвращай ничего кроме JSON-объекта. Схема ключей:\n' + schemaLines + '\nПоля "recipient_position"/"recipient_name", "sender_position"/"sender_short_name", "executor"/"phone" — это ПАРЫ: вариант под индексом i в одном поле соответствует варианту под индексом i в парном. "date" и "memo_number" не связаны.',
            temperature: 0.5,
        };
        const res = await streamAgentRequest(payload);
        const raw = parseMemoJson(res.answer);
        const out = normalizeFieldOptions(raw, keys);
        Object.keys(keys || []).forEach(k => {
            if ((out[keys[k]] || []).length) return;
            if (keys[k] === 'executor') {
                const names = (out.sender_short_name || []).slice(0, 3)
                    .map(n => (n || '').trim()).filter(Boolean);
                if (names.length) out.executor = names;
                else out.executor = ['Иванов И.И.', 'Петров П.П.', 'Сидоров С.С.'];
            } else if (keys[k] === 'phone') {
                out.phone = ['+7 (900) 123-45-67', '+7 (903) 555-01-02', '+7 (915) 777-35-40'];
            }
        });
        return out;
    },

    collectFields() {
        if (this.step !== 'fields') return;
        this.fields = {};
        this.botMsg.content.querySelectorAll('.memo-field').forEach(el => {
            const custom = el.querySelector('.memo-input');
            const key = custom?.dataset?.key || el.querySelector('.memo-option')?.dataset?.key;
            if (!key) return;
            const sel = el.querySelector('.memo-option.btn-primary');
            let val = custom && !custom.classList.contains('d-none') && custom.value.trim()
                ? custom.value.trim()
                : (sel ? sel.dataset.value : '');
            if (key === 'date' && val) {
                const m = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
                if (m) val = m[3] + '.' + m[2] + '.' + m[1];
            }
            this.fields[key] = val;
        });
        const bodyEl = document.getElementById('memo-edit-body');
        if (bodyEl) {
            const editedBody = bodyEl.value.trim();
            if (editedBody) {
                this.variants = [{ text: editedBody, sources: this.chosen != null && this.variants[this.chosen] ? (this.variants[this.chosen].sources || []) : [], idx: 1 }];
                this.chosen = 0;
            }
        }
        this.showResult();
    },

    async showResult() {
        this.step = 'check';
        const f = this.fields || {};
        const body = this.chosen != null && this.variants[this.chosen]
            ? this.variants[this.chosen].text
            : this.topic;
        const preview = renderMemoPreview({
            recipient_position: f.recipient_position || '',
            recipient_name: f.recipient_name || '',
            memo_number: f.memo_number || '',
            department: f.department || '',
            date: f.date || '',
            body: body,
            sender_position: f.sender_position || '',
            sender_short_name: f.sender_short_name || '',
            executor: f.executor || '',
            phone: f.phone || '',
        });
        this.botMsg.updateText('**Готовый черновик служебной записки:**');
        const previewBox = document.createElement('div');
        previewBox.className = 'memo-preview-text';
        previewBox.textContent = preview;
        this.botMsg.content.appendChild(previewBox);
        this.saveState();

        if (this.chosen != null && this.variants[this.chosen] && this.variants[this.chosen].sources) {
            this.botMsg.showSources(this.variants[this.chosen].sources);
        }

        const btns = document.createElement('div');
        btns.className = 'd-flex gap-2 flex-wrap mt-2';
        btns.innerHTML =
            '<button class="btn btn-sm btn-outline-primary" id="memo-edit-btn"><i class="bi bi-pencil"></i> Редактировать</button>' +
            '<button class="btn btn-sm btn-success" id="memo-save-btn"><i class="bi bi-download"></i> Скачать .docx и сохранить</button>' +
            '<button class="btn btn-sm btn-outline-secondary" id="memo-new-btn">Новая записка</button>';
        if (this.resultBtns) this.resultBtns.remove();
        this.resultBtns = btns;
        this.botMsg.bubble.appendChild(btns);

        document.getElementById('memo-edit-btn').addEventListener('click', () => this.editDraft());
        document.getElementById('memo-save-btn').addEventListener('click', () => this.saveAndDownload(preview));
        document.getElementById('memo-new-btn').addEventListener('click', () => {
            this.reset();
            Chat.appendMessage('Начнём новую служебную записку. Команда: /create <тема>', false);
        });
    },

    async saveAndDownload(previewText) {
        const f = this.fields || {};
        const bodyText = (this.fields.body || (this.chosen != null ? this.variants[this.chosen]?.text : '') || '').trim();
        try {
            const res = await fetch('/api/memo/docx', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    recipient_position: f.recipient_position || '',
                    recipient_name: f.recipient_name || '',
                    memo_number: f.memo_number || '',
                    department: f.department || '',
                    date: f.date || '',
                    body: bodyText,
                    sender_position: f.sender_position || '',
                    sender_short_name: f.sender_short_name || '',
                    executor: f.executor || '',
                    phone: f.phone || '',
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this.sendBot('Не удалось собрать файл: ' + (err.error || res.status));
                return;
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'sluzhebnaya_zapiska.docx';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            this.sendBot('Ошибка скачивания: ' + e.message);
            return;
        }
        await History.saveAnswerToFavorites(
            'Служебная записка: ' + this.topic,
            previewText,
            this.chosen != null ? (this.variants[this.chosen].sources || []) : []
        );
        await Chat.saveMessage(
            'Служебная записка: ' + this.topic,
            previewText,
            this.chosen != null ? (this.variants[this.chosen].sources || []) : []
        );
        this.sendBot('Служебная записка сохранена и файл .docx скачан.');
    },

    sendBot(text) {
        return Chat.appendMessage(text, false);
    },
};

// === Утилиты мастера ===
const MEMO_VARIANTS_SYSTEM_PROMPT = (
    'Ты — помощник, который генерирует варианты текста служебной записки. ' +
    'На основе заданной темы и предоставленных документов возвращаешь ОДИН JSON-объект ' +
    'вида {"variants": ["текст_варианта_1", "текст_варианта_2"], "sources": [{"file_name": "...", "file_path": "..."}]} ' +
    'с 3–5 вариантами (в каждом: адресат «Кому», служебная записка №, тема, основная часть, подпись). ' +
    'Стиль официально-деловой, на русском языке. ' +
    'Не добавляй ничего, кроме JSON.'
);

window.MEMO_VARIANTS_SYSTEM_PROMPT = MEMO_VARIANTS_SYSTEM_PROMPT;

function extractMemoVariants(raw) {
    const out = [];
    if (!raw || typeof raw !== 'object') return out;
    const push = (x) => {
        let text = null;
        if (typeof x === 'string') text = x;
        else if (x && typeof x === 'object') {
            text = x.text || x.body || x.variant || null;
        }
        text = text != null ? String(text).trim() : '';
        if (text && !out.some(v => v.text === text)) {
            const v = { text, sources: (x && Array.isArray(x.sources)) ? x.sources : [] };
            out.push(v);
        }
    };
    const list = Array.isArray(raw.variants) && raw.variants.length ? raw.variants
        : (Array.isArray(raw) && raw.length ? raw
        : (raw.variants ? null : [raw]));
    if (list && list.length) list.forEach(push);
    return out;
}

function parseMemoJson(text) {
    if (text == null) return {};
    if (typeof text === 'object') return text;
    const str = String(text);
    if (!str.trim()) return {};
    const structures = [];
    let i = 0;
    while (i < str.length) {
        let depth = 0, start = -1, inStr = false, esc = false;
        for (; i < str.length; i++) {
            const c = str[i];
            if (inStr) {
                if (esc) esc = false;
                else if (c === '\\') esc = true;
                else if (c === '"') inStr = false;
                continue;
            }
            if (c === '"') { inStr = true; continue; }
            if (c === '[' || c === '{') {
                if (depth === 0) start = i;
                depth++;
            } else if (c === ']' || c === '}') {
                depth--;
                if (depth === 0 && start >= 0) {
                    structures.push(str.substring(start, i + 1));
                    break;
                }
            }
        }
        i++;
    }
    const parsedStructures = [];
    for (const snippet of structures) {
        try {
            const parsed = JSON.parse(snippet);
            if (Array.isArray(parsed) || (parsed && typeof parsed === 'object')) {
                parsedStructures.push(parsed);
            }
        } catch (e) { /* ignore */ }
    }
    if (parsedStructures.length === 0) return {};
    if (parsedStructures.length > 1 && parsedStructures.every(p => Array.isArray(p))) {
        return parsedStructures;
    }
    return parsedStructures[0];
}

function normalizeFieldOptions(raw, keys) {
    const out = {};
    if (!raw || typeof raw !== 'object') return out;
    const push = (k, x) => {
        const s = x != null ? String(x).trim() : '';
        if (s && !isJunkVariant(k, s) && !(out[k] || []).some(e => e === s)) (out[k] = out[k] || []).push(s);
    };
    const isJunkVariant = (k, s) => {
        if (k !== 'executor' && k !== 'phone') return false;
        if (s.length > 80) return true;
        if (/\[.*\]/.test(s) && /фио|исполнител|xx/i.test(s)) return true;
        if (/Ответственные исполнител|\(XXX\)|xxx/i.test(s)) return true;
        if (k === 'phone' && !/\+?7\s*[\d\(\)\-\s]{5,}/.test(s)) return true;
        if (k === 'executor' && /отдел|служб|комисси|управлени|подразделен/i.test(s)) return true;
        return false;
    };
    const isFlatList = Array.isArray(raw) && raw.length &&
        raw.every(el => Array.isArray(el) || (el === null || typeof el !== 'object'));
    if (isFlatList) {
        const keyList = Array.isArray(keys) && keys.length ? keys : Object.keys(out);
        const flatRows = Array.isArray(raw) && raw.every(el => Array.isArray(el))
            ? raw : [raw];
        flatRows.forEach((list, idx) => {
            const k = keyList[idx];
            if (!k) return;
            if (Array.isArray(list)) list.forEach(x => push(k, x));
            else push(k, list);
        });
        return out;
    }
    if (Array.isArray(raw)) {
        raw.forEach(obj => {
            if (obj && typeof obj === 'object') {
                Object.keys(obj).forEach(k => {
                    const v = obj[k];
                    const val = Array.isArray(v) ? v : [v];
                    val.forEach(x => push(k, x));
                });
            }
        });
        return out;
    }
    Object.keys(raw || {}).forEach(k => {
        const v = raw[k];
        if (v && typeof v === 'object' && !Array.isArray(v)) {
            Object.keys(v).forEach(kk => {
                const val = Array.isArray(v[kk]) ? v[kk] : [v[kk]];
                val.forEach(x => push(k, x));
            });
        } else if (Array.isArray(v)) {
            v.forEach(x => push(k, x));
        } else if (v !== undefined && v !== null && String(v).trim()) {
            push(k, v);
        }
    });
    return out;
}

function renderMemoPreview(f) {
    const lines = [];
    lines.push('Кому: ' + (f.recipient_position || ''));
    if (f.recipient_name) lines.push('      ' + f.recipient_name);
    lines.push('Служебная записка № ' + (f.memo_number || '') + '/' + (f.department || '') + ' от ' + (f.date || ''));
    lines.push('');
    lines.push(f.body || '');
    lines.push('');
    if (f.sender_position || f.sender_short_name) {
        lines.push('С уважением, ' + (f.sender_position || '') + ' ' + (f.sender_short_name || ''));
    }
    return lines.join('\n');
}

function toDateInputValue(val) {
    const s = String(val || '').trim();
    const m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (m) return m[3] + '-' + m[2].padStart(2, '0') + '-' + m[1].padStart(2, '0');
    return s;
}

async function streamAgentRequest(payload) {
    const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.status === 503) {
        throw new Error('Индекс не готов — дождитесь окончания синхронизации');
    }
    if (!res.ok) {
        let detail = 'Ошибка';
        try { detail = (await res.json()).error || detail; } catch (e) { /* ignore */ }
        throw new Error(detail);
    }
    if (!res.body) throw new Error('Поток не поддерживается');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answer = '';
    let sources = [];
    async function read() {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value);
            const chunks = buffer.split('\n');
            buffer = chunks.pop();
            for (let chunk of chunks) {
                const line = chunk.trim();
                if (!line.startsWith('data: ')) continue;
                let data;
                try { data = JSON.parse(line.substring(6)); } catch (e) { continue; }
                if (data.type === 'sources') sources = data.data || [];
                else if (data.type === 'token') answer += data.data || '';
                else if (data.type === 'error') throw new Error(data.data || 'Ошибка генерации');
                else if (data.type === 'done') {
                    if (!answer) answer = data.answer || '';
                    sources = data.sources || sources;
                }
            }
        }
        if (buffer.trim()) {
            const line = buffer.trim();
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.substring(6));
                    if (data.type === 'token') answer += data.data || '';
                    else if (data.type === 'done') sources = data.sources || sources;
                } catch (e) { /* ignore */ }
            }
        }
        return { answer, sources };
    }
    return read();
}
