# RAG System — документация проекта

Репозиторий состоит из **двух независимых Python-проектов** (у каждого свой `.venv`):

| Проект | Назначение | Порт по умолчанию | Папка |
|---|---|---|---|
| **RAG System** | Ядро RAG: индексация документов, векторный поиск, RAG-ответы, Streaming API | `11455` (префикс `/rag`) | `RAG System/` |
| **RAG System Web UI** | Веб-интерфейс: чат, история, мастер служебной записки, админка | `80` (env `PORT`) | `RAG System Web UI/` |

Web UI работает **только через RAG API** ядра: корпус `out/` читает только ядро и его тесты.

---

## Оглавление

| # | Файл | Содержание |
|---|---|---|
| 01 | [`01-architecture.md`](01-architecture.md) | Общая архитектура, схемы, потоки данных, развёртывание |
| 02 | [`02-core-rag-system.md`](02-core-rag-system.md) | Ядро RAG System: модули, парсеры, провайдеры, конфиг, движок |
| 03 | [`03-web-ui.md`](03-web-ui.md) | Web UI: модули, сингл-страница, команды чата, админка |
| 04 | [`04-api-core.md`](04-api-core.md) | REST / SSE API ядра (префикс `/rag`) |
| 05 | [`05-api-webui.md`](05-api-webui.md) | API Web UI (префикс `/api`) |
| 06 | [`06-database.md`](06-database.md) | Схема SQLite-базы Web UI, сущности, мастера |
| 07 | [`07-memo-wizard.md`](07-memo-wizard.md) | Мастер служебной записки `/create` и шаблон `mmo.dotx` |
| 08 | [`08-installation.md`](08-installation.md) | Установка, запуск, переменные окружения |
| 09 | [`09-testing.md`](09-testing.md) | Тестирование (pytest, JS, headless) |
| 10 | [`10-build.md`](10-build.md) | Сборка onedir-EXE через PyInstaller |
| 11 | [`11-troubleshooting.md`](11-troubleshooting.md) | Частые проблемы и решения |
| 12 | [`12-git-and-conventions.md`](12-git-and-conventions.md) | Git-правила, соглашения, чек-листы |

HTML-версия документации лежит в папке [`../doc_html/`](../doc_html/00-README.html).

---

## Краткая сводка

- **Ядро** — Flask-приложение, стартует с `RAGEngine.initialize()`, синхронизация индекса идёт в фоновом потоке. Читает `rag_engine/settings.json`.
- **Провайдеры инференса**: Ollama (нативный API) и LM Studio (OpenAI-совместимый). Переключение по `provider`.
- **Форматы документов**: `.docx` (python-docx), `.doc` (Word COM), `.pdf` (ABBYY FineReader 15 + OCR). Для `.doc`/подсчёта страниц `.docx` и `.pdf` нужен Windows + установленный Word/FineReader.
- **Векторный поиск**: LlamaIndex + FAISS (`faiss-cpu`), чанки `SentenceSplitter`.
- **Web UI** — Flask + SQLAlchemy (SQLite) + Flask-Login + CSRF. Чат со SSE-стримингом, история диалогов и избранное, мастер `/create`, `/memos`, уведомления, обратная связь, смена пароля, ограничение доступа по расписанию (источник — ядро), админ-панель `/admin`.
- **Мастер записки** генерирует варианты тела через RAG и собирает `.docx` по шаблону `docx_templates/mmo.dotx` (поля из самого шаблона, пласхолдеры `{{ key }}`).
- **Сборка**: PyInstaller onedir-EXE для обоих проектов (`build.spec` + `build_all.ps1`), результат в `dist/`.

> Версии на момент написания документации: ядро `RAGEngine.VERSION = "26.10.13"`, Web UI `MEMO_JS_VERSION = "20261013-02"`.