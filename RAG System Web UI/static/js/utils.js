// === Общие утилиты ===

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

function renderMarkdown(text) {
    try {
        const html = marked.parse(text || '');
        return window.DOMPurify ? DOMPurify.sanitize(html) : html;
    } catch (e) {
        return (text || '').replace(/\n/g, '<br>');
    }
}

async function apiFetch(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) {
        let detail = 'Ошибка HTTP ' + res.status;
        try {
            const err = await res.json();
            detail = err.error || detail;
        } catch (e) { /* ignore */ }
        throw new Error(detail);
    }
    return res;
}

function showToast(message, type = 'success') {
    const div = document.createElement('div');
    div.className = 'alert alert-' + type + ' position-fixed bottom-0 end-0 m-3';
    div.style.zIndex = '2100';
    div.innerHTML = message;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 3000);
}

function copyText(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        if (btn) {
            const old = btn.innerHTML;
            btn.innerHTML = '<i class="bi bi-check-lg"></i>';
            setTimeout(() => { btn.innerHTML = old; }, 1500);
        }
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        if (btn) {
            const old = btn.innerHTML;
            btn.innerHTML = '<i class="bi bi-check-lg"></i>';
            setTimeout(() => { btn.innerHTML = old; }, 1500);
        }
    });
}

async function streamSSE(url, body, callbacks) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (res.status === 503) {
        let detail = 'Индекс не готов — дождитесь окончания синхронизации';
        try { const e = await res.json(); detail = e.error || detail; } catch (e) { /* ignore */ }
        throw new Error(detail);
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
            try { data = JSON.parse(line.substring(6)); } catch (e) { continue; }
            callbacks.onEvent?.(data);
            if (data.type === 'done') callbacks.onDone?.(data);
            if (data.type === 'error') callbacks.onError?.(data);
            if (data.type === 'sources') callbacks.onSources?.(data.data || []);
            if (data.type === 'reasoning') callbacks.onReasoning?.(data.data || '');
            if (data.type === 'token') callbacks.onToken?.(data.data || '');
        }
    }
    if (buffer.trim()) {
        const line = buffer.trim();
        if (line.startsWith('data: ')) {
            try {
                const data = JSON.parse(line.substring(6));
                callbacks.onEvent?.(data);
                if (data.type === 'done') callbacks.onDone?.(data);
                if (data.type === 'error') callbacks.onError?.(data);
                if (data.type === 'reasoning') callbacks.onReasoning?.(data.data || '');
                if (data.type === 'token') callbacks.onToken?.(data.data || '');
            } catch (e) { /* ignore */ }
        }
    }
}