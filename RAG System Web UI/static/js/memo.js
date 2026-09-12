// === Мастер генерации служебной записки (/create) ===

const MEMO_SYSTEM_PROMPT =
    "Ты — RAG-ассистент, который составляет официальную служебную записку " +
    "на основе предоставленных документов. " +
    "Оформи текст как СЛУЖЕБНУЮ ЗАПИСКУ: в начале — адресат (Кому), составитель (От), " +
    "заголовок с темой, затем основная часть с развёрнутым изложением предмета записки " +
    "(факты, цифры, даты, реквизиты документов из контекста), в конце — вывод и предложение. " +
    "Стиль официально-деловой, на русском языке, с абзацами. " +
    "Опирайся ТОЛЬКО на информацию из контекста ниже; " +
    "не выдумывай факты и не добавляй детали, которых нет в контексте. " +
    "Если нужных данных нет, честно укажи, какой информации недостаёт.";

// Для вариантов выдаём ТОЛЬКО тело записки — без шапки (Кому/От/№/дата) и без подписи.
const MEMO_BODY_SYSTEM_PROMPT =
    "Ты — RAG-ассистент, который составляет ТЕЛО (основной текст) официальной служебной записки " +
    "на основе предоставленных документов. " +
    "Выдавай ТОЛЬКО основную часть записки: раскрой тему с фактами, цифрами, датами " +
    "и реквизитами документов из контекста; в конце — обоснованный вывод и конкретное предложение. " +
    "НЕ добавляй шапку (Кому/От/№/дата), обращение, подпись, «С уважением» — только сам текст тела. " +
    "Стиль официально-деловой, на русском языке, с абзацами. " +
    "Опирайся ТОЛЬКО на информацию из контекста ниже; " +
    "не выдумывай факты и не добавляй детали, которых нет в контексте. " +
    "Если нужных данных нет, честно укажи, какой информации недостаёт.";

const MEMO_STATE_KEY = 'memo_session_state';

const MemoWizard = {
    step: null,          // 'topic' | 'variants' | 'review' | 'fields' | 'check'
    topic: '',
    fields: {},
    variants: [],        // [{text, sources}]
    chosen: null,        // индекс выбранного варианта
    botMsg: null,        // текущее сообщение бота в чате
    fieldOptions: {},    // варианты значений полей из RAG

    // === Сессия: сохранение и восстановление после обновления страницы ===

    saveState() {
        try {
            const st = {
                ts: Date.now(),
                step: this.step,
                topic: this.topic,
                variants: (this.variants || []).map(v => ({
                    text: v.text,
                    sources: v.sources || [],
                    idx: v.idx,
                })),
                chosen: this.chosen,
                fieldOptions: this.fieldOptions,
                fields: this.fields,
                fieldDefsNoBody: this.fieldDefsNoBody || [],
                keys: this.keys || [],
            };
            localStorage.setItem(MEMO_STATE_KEY, JSON.stringify(st));
        } catch (e) { /* localStorage недоступен */ }
    },

    clearState() {
        try { localStorage.removeItem(MEMO_STATE_KEY); } catch (e) { /* ignore */ }
    },

    // Восстанавливает незавершённый мастер. Возвращает true, если сессия найдена.
    async restoreSession() {
        let st = null;
        try { st = JSON.parse(localStorage.getItem(MEMO_STATE_KEY) || 'null'); } catch (e) { st = null; }
        if (!st || !st.topic) return false;

        this.step = st.step;
        this.topic = st.topic;
        this.variants = st.variants || [];
        this.chosen = st.chosen;
        this.fieldOptions = st.fieldOptions || {};
        this.fields = st.fields || {};
        this.fieldDefsNoBody = st.fieldDefsNoBody || [];
        this.keys = st.keys || [];

        this.botMsg = appendMessage('', false, []);
        this.botMsg.row.classList.add('memo-wide');

        if (this.step === 'fields') {
            const body = this.fields.body || (
                this.chosen != null && this.variants[this.chosen]
                    ? this.variants[this.chosen].text
                    : this.topic);
            this.renderFields(this.fieldDefsNoBody, this.fields, [body], true, true);
            this.sendBot('↩️ Сессия восстановлена: выберите вариант текста, при необходимости исправьте поля и нажмите «Далее».');
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
        this.clearState();
    },

    // Мастер перехватывает ввод только на шагах, где текст из строки чата
    // осмыслен (тема записки). На 'fields'/'check' ввод идёт кнопками и
    // полями окна, поэтому обычные запросы не должны попадать в мастер —
    // иначе после восстановления сессии чат отвечает подсказками мастера.
    isActive() {
        return this.step === 'topic' || this.step === 'variants' || this.step === 'review';
    },

    // Запуск: вернуть тему из ввода или запросить её.
    async start(inputText) {
        if (isGenerating || !inputsUnlocked) return;
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

    // Обработка ввода пользователя в зависимости от шага.
    async handleInput(text) {
        if (!text || isGenerating) return;
        if (this.step === 'topic') {
            this.topic = text;
            await this.offerVariants();
        } else if (this.step === 'variants') {
            // Пользователь предложил свой текст записки.
            await this.chooseCustom(text);
        } else if (this.step === 'review') {
            await this.askFields();
        } else if (this.step === 'fields') {
            this.sendBot('Заполните поля выше (выберите вариант или введите своё значение) и нажмите «Далее».');
        } else {
            this.sendBot('Нажмите кнопку «Скачать .docx и сохранить» ниже.');
        }
    },

    // === Шаг 1: единое окно — варианты тела + поля из RAG ===

    async offerVariants() {
        this.step = 'fields';
        this.botMsg = appendMessage('', false, []);
        this.botMsg.row.classList.add('memo-wide');
        this.botMsg.addDots();
        this.botMsg.updateText('Подбираю **варианты записки и значения полей** из базы знаний (RAG)...');
        isGenerating = true;
        unlockInputs(false);

        try {
            // 1. структура шаблона (поля)
            const f = await fetch('/api/memo/template');
            const data = await f.json().catch(() => ({ fields: [] }));
            const fieldDefs = Array.isArray(data.fields) && data.fields.length
                ? data.fields
                : [{ key: 'recipient_position', label: 'Кому (должность)', hint: '' },
                   { key: 'recipient_name', label: 'Кому (ФИО)', hint: '' },
                   { key: 'memo_number', label: 'Номер служебной записки', hint: '' },
                   { key: 'date', label: 'Дата', hint: '' },
                   { key: 'sender_position', label: 'От (должность)', hint: '' },
                   { key: 'sender_short_name', label: 'От (ФИО, кратко)', hint: '' }];
            this.fieldDefsNoBody = fieldDefs.filter(d => d.key !== 'body');
            this.keys = this.fieldDefsNoBody.map(d => d.key);

            // 2. варианты тела + варианты полей параллельно
            const styles = [
                'Составь краткое и формальное тело служебной записки по теме, используя данные из предоставленных документов (RAG).',
                'Составь подробное тело служебной записки по теме с фактами, цифрами, датами и ссылками на документы из RAG.',
                'Составь тело служебной записки по теме и предложи конкретные меры и обоснования на основе предоставленных документов (RAG).',
            ];
            const temps = [0.4, 0.7, 1.0];

            const bodyTasks = styles.map((style, i) =>
                streamAgentRequest({
                    prompt: `Тема служебной записки: «${this.topic}».\n${style}\nВыдай только тело записки, с абзацами, без шапки и подписи. Вариант ${i + 1}.`,
                    system_prompt: MEMO_BODY_SYSTEM_PROMPT,
                    temperature: temps[i],
                }).then(res => ({ text: res.answer, sources: res.sources, idx: i + 1 }))
            );

            const results = await Promise.all(bodyTasks);
            results.sort((a, b) => a.idx - b.idx);
            this.variants = results;
            this.chosen = 0;

            let fieldOptions = {};
            try {
                fieldOptions = await this.generateFieldOptions(this.keys);
            } catch (e) { /* поля останутся пустыми — можно ввести вручную */ }
            this.fieldOptions = fieldOptions;

            this.renderFields(this.fieldDefsNoBody, {}, [results[0] ? results[0].text : ''], true, true);
        } catch (e) {
            this.botMsg.updateText('Ошибка генерации: ' + e.message);
        } finally {
            isGenerating = false;
            unlockInputs(true);
        }
    },

    showVariants() {
        let html = `<div class="memo-variants">
            <h6>Варианты служебной записки по теме: <em>${escapeHtml(this.topic)}</em></h6>
            <em>Выберите один из вариантов (составлены по документам RAG) или введите свой текст:</em>`;
        this.variants.forEach((v, idx) => {
            html += `<div class="card mb-2">
                    <div class="card-header py-1"><strong>Вариант ${idx + 1}</strong></div>
                    <div class="card-body py-2 small memo-variant-text" style="white-space:pre-wrap">${escapeHtml(v.text)}</div>
                    <div class="card-footer py-1">
                        <button class="btn btn-sm btn-outline-primary memo-pick" data-idx="${idx}">Выбрать вариант ${idx + 1}</button>
                    </div>
                </div>`;
        });
        html += `<div class="mt-2">
                <label class="form-label small mb-0">Или введите свой вариант текста записки:</label>
                <textarea class="form-control form-control-sm" id="memo-custom-text" rows="4"
                          placeholder="Свой текст служебной записки..."></textarea>
                <div class="mt-2">
                    <button class="btn btn-sm btn-success" id="memo-custom-ok">Использовать свой текст</button>
                </div>
            </div></div>`;
        this.botMsg.updateText('');
        this.botMsg.content.innerHTML = html;
        this.botMsg.removeDots();

        this.botMsg.content.querySelectorAll('.memo-pick').forEach(btn => {
            btn.addEventListener('click', () => this.chooseVariant(parseInt(btn.dataset.idx, 10)));
        });
        document.getElementById('memo-custom-ok').addEventListener('click', () => {
            const ta = document.getElementById('memo-custom-text');
            const text = ta ? ta.value.trim() : '';
            if (text) this.chooseCustom(text);
        });
    },

    async chooseVariant(idx) {
        if (this.step !== 'variants') return;
        this.chosen = idx;
        await this.reviewBody();
    },

    async chooseCustom(text) {
        if (this.step !== 'variants') return;
        this.chosen = 0;
        this.variants = [{ text: text, sources: [], idx: 1 }];
        await this.reviewBody();
    },

    // === Шаг 2: согласование текста записки ===

    async reviewBody() {
        this.step = 'review';
        this.botMsg.updateText('');
        const body = this.variants[this.chosen].text;
        let html = `<div class="memo-review">
            <h6>Текст записки по теме: <em>${escapeHtml(this.topic)}</em></h6>
            <em>Отредактируйте текст прямо в поле ниже или подтвердите:</em>
            <textarea class="form-control mt-2 memo-review-text" id="memo-review-text" rows="10" style="white-space:pre-wrap"></textarea>
            <div class="d-flex gap-2 mt-2">
                <button class="btn btn-sm btn-success" id="memo-review-ok">Всё ок — далее поля</button>
                <button class="btn btn-sm btn-outline-danger" id="memo-review-reset">Вернуть исходный текст</button>
            </div>
            <div id="memo-review-status" class="small text-muted mt-2"></div>
        </div>`;
        this.botMsg.content.innerHTML = html;
        this.botMsg.removeDots();

        const textarea = document.getElementById('memo-review-text');
        textarea.value = body;
        const keepEdited = () => {
            // Пользователь правил текст руками — фиксируем как выбранный.
            const edited = textarea.value.trim();
            if (edited && edited !== this.variants[this.chosen].text) {
                this.variants = [{ text: edited, sources: this.variants[this.chosen].sources || [], idx: 1 }];
                this.chosen = 0;
            }
        };

        document.getElementById('memo-review-ok').addEventListener('click', () => {
            keepEdited();
            this.askFields();
        });
        document.getElementById('memo-review-reset').addEventListener('click', () => {
            const orig = this.variants[this.chosen].text;
            textarea.value = orig;
            const status = document.getElementById('memo-review-status');
            if (status) status.textContent = '';
        });
    },

    // === Шаг 3: поля шаблона — варианты из RAG ===

    async askFields() {
        this.step = 'fields';
        const f = await fetch('/api/memo/template');
        const data = await f.json().catch(() => ({ fields: [] }));
        // Сервер отдаёт структуру шаблона: [{key, label, hint}].
        const fieldDefs = Array.isArray(data.fields) && data.fields.length
            ? data.fields
            : [{ key: 'recipient_position', label: 'Кому (должность)', hint: '' },
               { key: 'recipient_name', label: 'Кому (ФИО)', hint: '' },
               { key: 'memo_number', label: 'Номер служебной записки', hint: '' },
               { key: 'date', label: 'Дата', hint: '' },
               { key: 'sender_position', label: 'От (должность)', hint: '' },
               { key: 'sender_short_name', label: 'От (ФИО, кратко)', hint: '' }];
        this.fieldDefsNoBody = fieldDefs.filter(d => d.key !== 'body');
        this.keys = this.fieldDefsNoBody.map(d => d.key);

        this.botMsg = appendMessage('', false, []);
        this.botMsg.row.classList.add('memo-wide');
        this.botMsg.addDots();
        this.botMsg.updateText('Подбираю **варианты полей** шаблона из базы знаний (RAG)...');

        let fieldOptions = {};
        try {
            fieldOptions = await this.generateFieldOptions(this.keys);
        } catch (e) { /* поля останутся пустыми — можно ввести вручную */ }
        this.fieldOptions = fieldOptions;

        this.renderFields(this.fieldDefsNoBody, {}, [], false);
    },

    // Отрисовка формы полей. prefill — текущие значения, body — текст тела.
    // showBodyPick=true — единое окно: выбор варианта тела + textarea тела + поля.
    renderFields(fieldDefsNoBody, prefill, bodies, includeBody, showBodyPick) {
        const fieldOptions = this.fieldOptions || {};
        let variantsHtml = '';
        if (showBodyPick && this.variants && this.variants.length) {
            variantsHtml = `<div class="mb-2">
                <em>Выберите вариант текста записки (из RAG) или отредактируйте его в поле ниже:</em>
                <div class="d-flex flex-wrap gap-1 mt-1 memo-variant-picks">` +
                this.variants.map((v, vi) =>
                    `<button type="button" class="btn btn-sm btn-outline-primary memo-body-pick${vi === (this.chosen || 0) ? ' btn-primary' : ''}" data-idx="${vi}">Вариант ${vi + 1}</button>`
                ).join('') + `</div>
            </div>`;
        }
        let html = `<div class="memo-fields">
            <h6>Служебная записка по теме: <em>${escapeHtml(this.topic)}</em></h6>
            ${variantsHtml}
            ${includeBody || showBodyPick ? `<label class="form-label small mb-0 mt-1">Текст служебной записки:</label>
            <textarea class="form-control form-control-sm memo-edit-body" id="memo-edit-body" rows="10" style="white-space:pre-wrap">${escapeHtml(bodies[0] || '')}</textarea>` : ''}
            <em>Поля «Дата» и «Номер» заполняются вручную, остальные — вариантом из базы знаний (RAG) или своим значением:</em>
            <div class="mb-2 mt-2">`;
        fieldDefsNoBody.forEach(def => {
            const key = def.key;
            const label = def.label || key;
            const hint = def.hint || '';
            const manualOnly = key === 'date' || key === 'memo_number';
            const isDate = key === 'date';
            const opts = (fieldOptions[key] || []).filter(v => v && String(v).trim());
            const cur = prefill[key] || '';
            let optionsHtml = '';
            const optionButtons = [];
            if (!manualOnly && opts.length) {
                opts.forEach((opt, oi) => {
                    const selected = cur === String(opt).trim() ? ' btn-primary' : '';
                    optionButtons.push(
                        `<button type="button" class="btn btn-sm btn-outline-secondary memo-option${selected}" data-key="${key}" data-oi="${oi}" data-value="${escapeHtml(opt)}">${escapeHtml(opt)}</button>`
                    );
                });
                optionsHtml = `<div class="d-flex flex-wrap gap-1 mb-1 memo-options" data-key="${key}">` +
                    optionButtons.join('') + `</div>`;
            }
            const inputVal = isDate ? toDateInputValue(cur) : cur;
            const hasChosen = optionButtons.length && cur && (prefill[key] || '').trim() &&
                opts.some(o => String(o).trim() === String(prefill[key]).trim());
            const inputVisible = manualOnly || !hasChosen;
            html += `<div class="memo-field mb-2">
                <div class="d-flex align-items-center gap-2">
                    <label class="form-label small mb-0">${escapeHtml(label)}</label>
                    ${manualOnly ? '' : `<button type="button" class="btn btn-link btn-sm p-0 memo-custom-toggle" data-key="${key}">ввести своё</button>`}
                </div>
                ${optionsHtml}
                <input type="${isDate ? 'date' : 'text'}" class="form-control form-control-sm memo-input ${inputVisible ? '' : 'd-none'}" data-key="${key}" value="${escapeHtml(inputVal)}"
                    ${isDate ? '' : (hint ? ` placeholder="${escapeHtml(hint)}"` : '')} placeholder="${manualOnly && !isDate ? 'Заполните вручную' : 'Свой вариант'}">
            </div>`;
        });
        html += `</div>
            <div class="d-flex gap-2 flex-wrap">
                <button class="btn btn-sm btn-primary" id="memo-choice-next">${includeBody ? 'Далее' : 'Далее'}</button>
                ${includeBody && !showBodyPick ? `<button class="btn btn-sm btn-outline-secondary" id="memo-edit-cancel">Отмена</button>` : ''}
                <button class="btn btn-sm btn-outline-secondary" id="memo-choice-random">Предложить поля из RAG заново</button>
            </div>
            <div id="memo-choice-status" class="small text-muted mt-2"></div>
        </div>`;
        this.botMsg.updateText('');
        this.botMsg.content.innerHTML = html;
        this.botMsg.removeDots();
        const _applyDraftBtn = (self) => {
            self.botMsg.content.querySelectorAll('.memo-body-pick').forEach(btn => {
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
        };
        if (showBodyPick && this.variants && this.variants.length) _applyDraftBtn(this);

        // Связанные пары полей: выбор варианта в одном автоподтягивает вариант в другом.
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
            const input = this.botMsg.content.querySelector(`input[data-key="${key}"]`);
            if (input) { input.value = ''; input.classList.add('d-none'); }
            this.botMsg.content.querySelectorAll(`.memo-option[data-key="${key}"]`)
                .forEach(b => b.classList.remove('btn-primary'));
            btn.classList.add('btn-primary');
            this.fields[key] = btn.dataset.value;
            // Автоподстановка связанного поля (по индексу варианта).
            const linkedKey = linkedPairs[key];
            if (linkedKey) {
                const oi = btn.dataset.oi;
                const linked = this.botMsg.content.querySelector(`.memo-option[data-key="${linkedKey}"][data-oi="${oi}"]`);
                if (linked && !linked.classList.contains('btn-primary')) selectOption(linked);
                else if (linked) this.fields[linkedKey] = linked.dataset.value;
            }
            this.saveState();
        };
        // Клик по варианту — выбрать.
        this.botMsg.content.querySelectorAll('.memo-option').forEach(btn => {
            btn.addEventListener('click', () => selectOption(btn));
        });
        // «ввести своё» — раскрыть поле ввода (снимает выбор варианта).
        this.botMsg.content.querySelectorAll('.memo-custom-toggle').forEach(toggle => {
            toggle.addEventListener('click', () => {
                const key = toggle.dataset.key;
                const input = this.botMsg.content.querySelector(`input[data-key="${key}"]`);
                if (input) {
                    input.classList.toggle('d-none');
                    if (!input.classList.contains('d-none')) input.focus();
                }
                this.botMsg.content.querySelectorAll(`.memo-option[data-key="${key}"]`)
                    .forEach(b => b.classList.remove('btn-primary'));
                this.fields[key] = '';
                this.saveState();
            });
        });
        // Ручной ввод значений полей и правка текста записки — фиксируем в состоянии.
        this.botMsg.content.querySelectorAll('.memo-input').forEach(input => {
            input.addEventListener('input', () => {
                this.fields[input.dataset.key] = input.value;
                this.saveState();
            });
        });
        const bodyTa = document.getElementById('memo-edit-body');
        if (bodyTa) {
            bodyTa.addEventListener('input', () => {
                this.fields.body = bodyTa.value;
                this.saveState();
            });
        }
        // Первый показ — сохраняем тело как начальное значение сессии.
        if (bodyTa) {
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
                    const input = this.botMsg.content.querySelector(`input[data-key="${k}"]`);
                    if (input && vals[k] && vals[k].length) input.value = vals[k][0];
                    const opt = this.botMsg.content.querySelector(`.memo-option[data-key="${k}"]`);
                    if (opt) selectOption(opt);
                });
                status.textContent = 'Поля обновлены. Проверьте и нажмите «Далее».';
            } catch (e) {
                status.textContent = 'Не удалось подобрать поля из RAG: ' + e.message;
            }
        };

        document.getElementById('memo-choice-next').addEventListener('click', () => this.collectFields());
        if (includeBody && document.getElementById('memo-edit-cancel')) {
            document.getElementById('memo-edit-cancel').addEventListener('click', () => this.showResult());
        }
        document.getElementById('memo-choice-random').addEventListener('click', fillRandom);
    },

    // Возврат к редактированию тела и полей из превью.
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
        // Схема JSON строится динамически из ключей шаблона, отданных сервером.
        const schemaLines = JSON.stringify(
            Object.fromEntries(keys.map(k => [k, ['вариант1', 'вариант2']])),
            null, 2);
        const payload = {
            // Prompt — это RAG-запрос: по теме система ищет нужные документы, а затем
            // из контекста берутся реалистичные данные для полей.
            prompt: `Служебная записка: ${this.topic}. Подготовь данные для её шапки — кому адресована, номер, дата, от кого. Используй сведения из контекста документов (ФИО, должности, отделы, даты).`,
            system_prompt: 'Ты — помощник, который подбирает данные для шаблонов деловых документов только из контекста. Верни ОДИН JSON-объект вида {"ключ": ["вариант1", "вариант2"], ...} для ВСЕХ ключей из схемы, по 2-3 варианта на каждый ключ. НЕ возвращай массивы списком и NИЧЕГО кроме этого JSON-объекта — без пояснений и обрамляющего текста. Схема ключей:\n' + schemaLines + '\nВАЖНО: поля "recipient_position" и "recipient_name" (также "sender_position" и "sender_short_name", "executor" и "phone") — это ПАРЫ: вариант под индексом i в одном поле должен соответствовать варианту под индексом i в парном (один и тот же человек, его должность/телефон). Поля "date" и "memo_number" не связаны с другими.',
            temperature: 0.3,
        };
        const res = await streamAgentRequest(payload);
        const raw = parseMemoJson(res.answer);
        return normalizeFieldOptions(raw, keys);
    },

    collectFields() {
        if (this.step !== 'fields') return;
        this.fields = {};
        this.botMsg.content.querySelectorAll('.memo-field').forEach(el => {
            const custom = el.querySelector('.memo-input');
            const key = custom?.dataset.key || el.querySelector('.memo-option')?.dataset.key;
            if (!key) return;
            const sel = el.querySelector('.memo-option.btn-primary');
            let val = custom && !custom.classList.contains('d-none') && custom.value.trim()
                ? custom.value.trim()
                : (sel ? sel.dataset.value : '');
            if (key === 'date' && val) {
                // Виджет даёт ISO (YYYY-MM-DD) — приводим к ДД.ММ.ГГГГ.
                const m = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
                if (m) val = `${m[3]}.${m[2]}.${m[1]}`;
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

    // === Шаг 4: превью и сохранение ===

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

        if (this.chosen != null && this.variants[this.chosen].sources) {
            this.botMsg.showSources(this.variants[this.chosen].sources);
        }

        const btns = document.createElement('div');
        btns.className = 'd-flex gap-2 flex-wrap mt-2';
        btns.innerHTML = `
            <button class="btn btn-sm btn-outline-primary" id="memo-edit-btn"><i class="bi bi-pencil"></i> Редактировать</button>
            <button class="btn btn-sm btn-success" id="memo-save-btn"><i class="bi bi-download"></i> Скачать .docx и сохранить</button>
            <button class="btn btn-sm btn-outline-secondary" id="memo-new-btn">Новая записка</button>`;
        if (this.resultBtns) this.resultBtns.remove();
        this.resultBtns = btns;
        this.botMsg.bubble.appendChild(btns);

        document.getElementById('memo-edit-btn').addEventListener('click', () => this.editDraft());
        document.getElementById('memo-save-btn').addEventListener('click', () => this.saveAndDownload(preview));
        document.getElementById('memo-new-btn').addEventListener('click', () => {
            this.reset();
            appendMessage('Начнём новую служебную записку. Команда: /create <тема>', false);
        });
    },

    async saveAndDownload(previewText) {
        const f = this.fields || {};
        this.fields.body = previewText;
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
                    body: previewText,
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

        await saveAnswerToFavorites(
            'Служебная записка: ' + this.topic,
            previewText,
            this.chosen != null ? (this.variants[this.chosen].sources || []) : []
        );
        await saveConversation(
            'Служебная записка: ' + this.topic,
            previewText,
            this.chosen != null ? (this.variants[this.chosen].sources || []) : []
        );
        this.sendBot('✅ Служебная записка сохранена (раздел «Ответы» и диалог истории) и файл .docx скачан.');
        this.reset();
    },

    sendBot(text) {
        const m = appendMessage(text, false, []);
        return m;
    },
};

// === Утилиты мастера ===

function parseMemoJson(text) {
    if (text == null) return {};
    // RAG может прислать уже готовый объект/массив напрямую (data.answer).
    if (typeof text === 'object') return text;
    const str = String(text);
    if (!str.trim()) return {};

    // Собираем все независимые top-level структуры [ ... ] / { ... } в тексте
    // (балансируя скобки с учётом строк и экранирования). Если массив один,
    // он может быть и объектом-набором, и плоским списком полей.
    const structures = [];
    let i = 0;
    while (i < str.length) {
        let depth = 0;
        let start = -1;
        let inStr = false;
        let esc = false;
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
    // Несколько независимых массивов (плоский список полей без ключей)
    // — возвращаем как массив списков.
    if (parsedStructures.length > 1 && parsedStructures.every(p => Array.isArray(p))) {
        return parsedStructures;
    }
    return parsedStructures[0];
}

// Приводит ответ RAG к виду {key: [варианты...], ...}.
// RAG может вернуть: 1) объект {key: [...], ...}; 2) массив готовых наборов
// [{key: значение}, ...]; 3) плоский список списков без ключей по порядку keys.
function normalizeFieldOptions(raw, keys) {
    const out = {};
    if (!raw || typeof raw !== 'object') return out;
    const push = (k, x) => {
        const s = x != null ? String(x).trim() : '';
        if (s && !(out[k] || []).some(e => e === s)) (out[k] = out[k] || []).push(s);
    };
    // Плоский список (списков) без ключей — по порядку keys. Элементы: строки/числа
    // или вложенные списки, НО не объекты-наборы полей.
    const isFlatList = Array.isArray(raw) && raw.length &&
        raw.every(el => Array.isArray(el) || (el === null || typeof el !== 'object'));
    if (isFlatList) {
        const keyList = Array.isArray(keys) && keys.length ? keys : Object.keys(out);
        const flatRows = Array.isArray(raw) && raw.every(el => Array.isArray(el))
            ? raw
            : [raw];
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
    // Вложенный объект {key: {вариантNN: x}} или обычный объект со списками.
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
    lines.push(`Кому: ${f.recipient_position || ''}`);
    if (f.recipient_name) lines.push(`      ${f.recipient_name}`);
    lines.push(`Служебная записка № ${f.memo_number || ''}/${f.department || ''} от ${f.date || ''}`);
    lines.push('');
    lines.push(f.body || '');
    lines.push('');
    if (f.sender_position || f.sender_short_name) {
        lines.push(`С уважением, ${f.sender_position || ''} ${f.sender_short_name || ''}`);
    }
    if (f.executor || f.phone) {
        lines.push(`Исполнитель: ${f.executor || ''} ${f.phone || ''}`.trim());
    }
    return lines.join('\n');
}

// «27.09.2026» → «2026-09-27» для виджета <input type="date"> (пусто при неверном формате).
function toDateInputValue(val) {
    const s = String(val || '').trim();
    const m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (m) return `${m[3]}-${String(m[2]).padStart(2, '0')}-${String(m[1]).padStart(2, '0')}`;
    return s;
}

// Потоковый запрос к /rag/agent/stream, собирает текст и источники.
async function streamAgentRequest(payload) {
    const res = await fetch('/rag/agent/stream', {
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
                try {
                    data = JSON.parse(line.substring(6));
                } catch (e) { continue; }
                if (data.type === 'sources') {
                    sources = data.data || [];
                } else if (data.type === 'token') {
                    answer += data.data || '';
                } else if (data.type === 'error') {
                    throw new Error(data.data || 'Ошибка генерации');
                } else if (data.type === 'done') {
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