import logging
import threading

from flask import Flask, request, jsonify, Response

from rag_engine.rag_engine import RAGEngine

app = Flask(__name__)
engine = RAGEngine()

# Список корневых эндпоинтов сервиса
API_PREFIX = "/rag"

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
#  Health / metadata
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/info", methods=["GET"])
def info():
    """Общая информация о сервисе: движок, статус, окружение."""
    return jsonify({
        "service": "RAG System",
        "engine": "IndexDocuments RAGEngine",
        "version": getattr(engine, "version", "26.06.25"),
        "provider": engine.cfg.provider,
        "initialized": engine.is_initialized,
        "syncing": engine.is_syncing,
        "document_count": engine.get_document_count(),
        "status_backend": engine.status_backend,
    })


@app.route(f"{API_PREFIX}/health", methods=["GET"])
def health():
    """Проверка доступности сервиса."""
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
#  API для внешних агентов
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/agent/stream", methods=["POST"])
def agent_stream():
    """Потоковое API для внешних агентов (SSE).

    Принимает агрегированный промпт агента и возвращает ответ LLM на основе
    найденного в RAG контекста. События: token / sources / done / error.

    Тело запроса (JSON):
        prompt: str          — промпт/вопрос агента (обязательно)
        system_prompt: str   — системная инструкция для LLM (опционально)
        top_k: int           — сколько релевантных фрагментов использовать
        temperature: float   — температура LLM (опционально)
    """
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or data.get("question") or "").strip()
    if not prompt:
        return jsonify({"error": "Поле 'prompt' обязательно"}), 400

    if not engine.is_initialized or engine.index is None:
        return jsonify({
            "error": "Индекс не готов",
            "hint": "Дождитесь завершения синхронизации",
        }), 503

    system_prompt = data.get("system_prompt") or None
    top_k = data.get("top_k")
    temperature = data.get("temperature")

    def generate():
        for event in engine.agent_stream(
            prompt,
            system_prompt=system_prompt,
            top_k=top_k,
            temperature=temperature,
        ):
            payload = {"type": event["type"], "data": event.get("data", "")}
            if event["type"] == "done":
                payload["answer"] = event.get("answer", "")
                payload["sources"] = event.get("sources", [])
                payload["prompt"] = event.get("prompt", "")
            yield f"data: {__import__('json').dumps(payload, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
#  Индексация / синхронизация
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/index", methods=["POST"])
def start_index():
    """Запускает синхронизацию индекса. query-параметр 'reset=true' очищает кэш."""
    reset = request.args.get("reset", "false").lower() == "true"
    if engine.is_syncing:
        return jsonify({"status": "already_syncing", "message": "Синхронизация уже идёт"}), 200
    engine.start_sync(is_remove=reset)
    return jsonify({"status": "started", "reset": reset, "message": "Синхронизация запущена"}), 202


@app.route(f"{API_PREFIX}/index/status", methods=["GET"])
def index_status():
    """Текущий статус синхронизации."""
    return jsonify({
        "is_syncing": engine.is_syncing,
        "status": engine.sync_status,
        "progress": engine.sync_progress,
        "sync_files": engine.sync_file,
        "initialized": engine.is_initialized,
        "document_count": engine.get_document_count(),
        "index_updated": engine.get_data_bd(),
    })


@app.route(f"{API_PREFIX}/index/stats", methods=["GET"])
def index_stats():
    """Статистика по проиндексированным документам."""
    return jsonify({
        "document_count": engine.get_document_count(),
        "index_updated": engine.get_data_bd(),
        "status": engine.sync_status,
    })


# ---------------------------------------------------------------------------
#  Папки для сканирования
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/folders", methods=["GET"])
def get_folders():
    return jsonify({"folders": engine.get_config().get("sync_folders", [])})


@app.route(f"{API_PREFIX}/folders", methods=["POST"])
def set_folders():
    data = request.get_json(silent=True) or {}
    folders = data.get("folders")
    if not isinstance(folders, list):
        return jsonify({"error": "Поле 'folders' должно быть списком"}), 400
    engine.set_sync_folders(folders)
    return jsonify({"ok": True, "folders": folders})


# ---------------------------------------------------------------------------
#  Конфигурация
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/config", methods=["GET"])
def get_config():
    return jsonify(engine.get_config())


@app.route(f"{API_PREFIX}/config", methods=["PATCH"])
def patch_config():
    """Частичное обновление конфигурации движка."""
    data = request.get_json(silent=True) or {}
    allowed = {
        "provider", "api_key",
        "context_window", "chunk_size", "chunk_overlap", "similarity_top_k",
        "page_limit", "size_limit_mb", "embedding_dim", "llm", "llm_embed",
        "llm_keywords", "url",
    }
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": "Нет поддерживаемых полей", "allowed": sorted(allowed)}), 400
    if "provider" in payload and payload["provider"] not in ("ollama", "lmstudio"):
        return jsonify({"error": "provider должен быть 'ollama' или 'lmstudio'"}), 400
    try:
        result = engine.update_config(**payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    changed = result["changed"]
    return jsonify({"ok": True, "changed": changed, "config": engine.get_config()})


@app.route(f"{API_PREFIX}/config/reset", methods=["POST"])
def reset_config():
    """Возвращает конфигурацию к значениям по умолчанию и пересинхронизирует индекс."""
    engine.cfg = engine.cfg.__class__()
    engine.cfg.save()
    engine.start_sync(is_remove=True)
    return jsonify({"ok": True, "config": engine.get_config()})


# ---------------------------------------------------------------------------
#  Провайдер / модели
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/models", methods=["GET"])
def models():
    """Список доступных моделей бэкенда (эмбеддинги, LLM, извлечение ключевых слов)."""
    if not engine.status_backend:
        # Бэкенд был недоступен — пробуем проверить ещё раз (например, только что
        # запустили LM Studio/Ollama) и отдаём модель/статус актуального состояния.
        engine.refresh_backend_models()
    return jsonify({
        "provider": engine.cfg.provider,
        "status_backend": engine.status_backend,
        "models": engine.get_backend_models(),
    })

@app.route(f"{API_PREFIX}/provider", methods=["GET"])
def get_provider():
    """Текущий провайдер и его параметры."""
    return jsonify({
        "provider": engine.cfg.provider,
        "status_backend": engine.status_backend,
        "models": engine.get_backend_models(),
    })

@app.route(f"{API_PREFIX}/provider", methods=["POST"])
def set_provider():
    """Смена провайдера (ollama | lmstudio)."""
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").lower().strip()
    if provider not in ("ollama", "lmstudio"):
        return jsonify({"error": "Провайдер должен быть 'ollama' или 'lmstudio'"}), 400
    engine.update_config(provider=provider)
    return jsonify({"ok": True, "provider": provider, "config": engine.get_config()})


@app.route(f"{API_PREFIX}/engine/status", methods=["GET"])
def engine_status():
    """Полный статус движка."""
    return jsonify(engine.get_status())


# ---------------------------------------------------------------------------
#  Утилиты
# ---------------------------------------------------------------------------
@app.route(f"{API_PREFIX}/parse", methods=["POST"])
def parse_file():
    """Парсинг одного файла (для отладки/проверки)."""
    data = request.get_json(silent=True) or {}
    path = data.get("file_path")
    if not path:
        return jsonify({"error": "Поле 'file_path' обязательно"}), 400
    import os
    if not os.path.exists(path):
        return jsonify({"error": f"Файл не найден: {path}"}), 404
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            from rag_engine.docx_parser import DocxParser
            parser = DocxParser(path)
        elif ext == ".doc":
            from rag_engine.doc_parser import DocParser
            parser = DocParser(path)
        elif ext == ".pdf":
            from rag_engine.pdf_parser import PdfParser
            parser = PdfParser(path)
        else:
            return jsonify({"error": "Неподдерживаемый формат. Используйте .doc, .docx, .pdf"}), 400
        page_count, text = parser.parse()
        if text is None:
            content = "_Документ пуст, слишком большой или содержит только изображения._"
        else:
            content = text
        return jsonify({"ok": True, "page_count": page_count, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route(f"{API_PREFIX}/parse/stream", methods=["POST"])
def parse_file_stream():
    """Парсинг одного файла с потоковой выдачей (по абзацам)."""
    data = request.get_json(silent=True) or {}
    path = data.get("file_path")
    if not path:
        return jsonify({"error": "Поле 'file_path' обязательно"}), 400

    def generate():
        import os
        if not os.path.exists(path):
            yield f"data: {__import__('json').dumps({'type': 'error', 'data': 'Файл не найден'}, ensure_ascii=False)}\n\n"
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".docx":
                from rag_engine.docx_parser import DocxParser
                parser = DocxParser(path)
            elif ext == ".doc":
                from rag_engine.doc_parser import DocParser
                parser = DocParser(path)
            elif ext == ".pdf":
                from rag_engine.pdf_parser import PdfParser
                parser = PdfParser(path)
            else:
                yield f"data: {__import__('json').dumps({'type': 'error', 'data': 'Неподдерживаемый формат'}, ensure_ascii=False)}\n\n"
                return
            page_count, text = parser.parse()
            text = text or ""
            for para in text.split("\n\n"):
                if para.strip():
                    chunk = {"type": "chunk", "data": para}
                    yield f"data: {__import__('json').dumps(chunk, ensure_ascii=False)}\n\n"
            yield f"data: {__import__('json').dumps({'type': 'done', 'page_count': page_count}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {__import__('json').dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("🚀 Запуск RAG System API...")
    engine.initialize()
    print("🌐 RAG API доступен по адресу: http://127.0.0.1:11455/rag")
    app.run(debug=False, host="0.0.0.0", port=11455, use_reloader=False)
