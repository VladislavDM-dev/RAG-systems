# RAG System

Отдельное приложение-сервис на базе RAG (Retrieval-Augmented Generation), предоставляющее **собственный HTTP API** (Flask) без веб-интерфейса.

Сервис индексирует документы (`.doc`, `.docx`, `.pdf`) из указанных папок, строит векторный индекс в **FAISS** через **LlamaIndex**, а генерацию ответов выполняет через выбранный локальный провайдер:

- **Ollama** — нативный API;
- **LM Studio** — OpenAI-совместимый API.

Взаимодействие происходит через собственный REST API `/rag/*`; веб-интерфейс
(чат и мастер служебных записок) живёт в отдельном проекте
[`RAG System Web UI`](../RAG%20System%20Web%20UI/README.md) и проксирует запросы сюда.

---

## Установка

```bash
cd "C:\Scripts\RAG systems\RAG System"
pip install -r requirements.txt
```

Требования:
- Windows (используется COM для конвертации `.doc` и подсчёта страниц `.docx`)
- Запущенный **Ollama** **или** **LM Studio** (в зависимости от выбранного провайдера) с моделями
- Для OCR `.pdf` — **ABBYY FineReader 15** (путь `C:\Program Files (x86)\ABBYY FineReader 15\FineCmd.exe`)

## Запуск

```bash
.\.venv\Scripts\python.exe -X utf8 app.py
```

Сервис поднимется на `http://127.0.0.1:11455/rag`.

## Тестирование

```bash
.\.venv\Scripts\python.exe -m pytest
```

Тесты не требуют запущенного Ollama/LM Studio: парсинг проверяется на реальных
файлах из каталога `out` (служебные записки `.docx`), API — на Flask test client.
Каталог `out` должен находиться рядом с проектом (`C:\Scripts\RAG systems\out`).

При прогоне файл `rag_engine/settings.json` временно приводится к значениям по
умолчанию, а в конце — восстанавливается исходное содержимое.

---

## Провайдеры

### Ollama
- URL по умолчанию: `http://172.30.99.77:11434`
- Формат: нативный Ollama API
- Модель эмбеддингов должна поддерживать `embedding`, LLM — чат.

### LM Studio
- URL по умолчанию: `http://localhost:1234/v1`
- Формат: OpenAI-совместимый API (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`)
- В настройках LM Studio обязательно включите локальный сервер (Developer → Start server).
- `api_key` можно оставить пустым (LM Studio принимает любой) или задать в настройках сервера.

Смена провайдера: см. раздел API → `POST /rag/provider`.

> **Примечание:** при смене провайдера, если `url` не указан явно и равен адресу
> по умолчанию прежнего провайдера, он автоматически заменяется на адрес по умолчанию
> нового (`ollama` → `http://127.0.0.1:11434`, `lmstudio` → `http://127.0.0.1:1234/v1`).
> Указанный вручную `url` при смене провайдера сохраняется.
>
> Если модели `llm`, `llm_keywords` или `llm_embed` заданы не явно и отсутствуют
> у нового провайдера, они автоматически заменяются на первую подходящую модель
> из его списка (LLM / эмбеддинги).

---

## Конфигурация

Конфигурация лежит в `rag_engine/settings.json` (создаётся автоматически) и управляется через API `PATCH /rag/config`.

Основные параметры:

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `provider` | `ollama` | Провайдер: `ollama` или `lmstudio` |
| `context_window` | 4096 | Окно контекста LLM |
| `chunk_size` | 256 | Размер чанка |
| `chunk_overlap` | 50 | Перекрытие чанков |
| `similarity_top_k` | 10 | Сколько узлов брать |
| `page_limit` | 10 | Макс. страниц документа |
| `size_limit_mb` | 5 | Макс. размер файла |
| `embedding_dim` | 768 | Размерность векторной модели |
| `llm` | `qwen3:4b` | Модель генерации |
| `llm_embed` | `nomic-embed-text-v2-moe:latest` | Модель эмбеддингов |
| `llm_keywords` | `llama3.2:3b` | Модель извлечения ключевых слов |
| `url` | `http://172.30.99.77:11434` | Адрес API провайдера |
| `api_key` | `` | API-ключ (LM Studio / OpenAI-совместимые) |
| `sync_folders` | `[]` | Папки для сканирования |

> **Важно:** при смене `llm_embed` или `embedding_dim` индекс перестраивается с нуля автоматически.

---

## API

Все эндпоинты имеют префикс `/rag`.

### Health / metadata

#### `GET /rag/health`
Проверка доступности.
```json
{ "status": "ok" }
```

#### `GET /rag/info`
Информация о сервисе и статус.
```json
{
  "service": "RAG System",
  "version": "26.06.25",
  "provider": "ollama",
  "initialized": true,
  "syncing": false,
  "document_count": 42,
  "status_backend": true
}
```

#### `GET /rag/engine/status`
Полный статус движка (включая прогресс синхронизации, файлы в обработке, индекс).

---

### Провайдер

#### `GET /rag/provider`
Текущий провайдер и модели.
```json
{
  "provider": "ollama",
  "status_backend": true,
  "models": { "all": [...], "thinking": [...], "embedding": [...] }
}
```

#### `POST /rag/provider`
Смена провайдера.
```json
{ "provider": "lmstudio" }
```
Ответ:
```json
{ "ok": true, "provider": "lmstudio", "config": {...} }
```

---

### Индексация

#### `POST /rag/index`
Запуск синхронизации индекса.
- `?reset=true` — очистить кэш индекса перед синхронизацией.
- Возвращает `202` при старте.

#### `GET /rag/index/status`
Статус синхронизации (прогресс, файлы в обработке).

#### `GET /rag/index/stats`
Статистика индекса (кол-во документов, время обновления).

---

### Папки сканирования

#### `GET /rag/folders`
```json
{ "folders": ["C:\\Docs"] }
```

#### `POST /rag/folders`
Установить папки сканирования.
```json
{ "folders": ["C:\\Docs", "D:\\Ark"] }
```

---

### Конфигурация

#### `GET /rag/config`
Текущая конфигурация.

#### `PATCH /rag/config`
Частичное обновление. Допустимые поля: `provider`, `context_window`, `chunk_size`, `chunk_overlap`, `similarity_top_k`, `page_limit`, `size_limit_mb`, `embedding_dim`, `llm`, `llm_embed`, `llm_keywords`, `url`, `api_key`.

```json
{ "llm": "qwen3:8b", "similarity_top_k": 15 }
```
Ответ:
```json
{ "ok": true, "changed": ["llm","similarity_top_k"], "config": {...} }
```

#### `POST /rag/config/reset`
Сброс конфигурации к значениям по умолчанию и пересинхронизация индекса.

---

### Модели и парсинг

#### `GET /rag/models`
Список моделей бэкенда (все / thinking / embedding) по текущему провайдеру.

#### `POST /rag/parse`
Парсинг одного файла (для отладки).
```json
{ "file_path": "C:\\Docs\\file.docx" }
```
Ответ: `{ "ok": true, "page_count": 5, "content": "...markdown..." }`

#### `POST /rag/parse/stream`
Парсинг файла с потоковой выдачей по абзацам (SSE, события `chunk` / `done` / `error`).

---

## Структура проекта

```
RAG System/
├── app.py                     # Flask API-сервис (собственные эндпоинты /rag)
├── requirements.txt
├── README.md
└── rag_engine/                # Движок как Python-пакет
    ├── __init__.py
    ├── config.py              # Dataclass-конфигурация (settings.json)
    ├── providers.py           # Абстракция провайдеров (Ollama / LM Studio)
    ├── rag_engine.py          # RAGEngine: индексация + поиск
    ├── docx_parser.py         # .docx → Markdown
    ├── doc_parser.py          # .doc → .docx (COM) → Markdown
    ├── pdf_parser.py          # .pdf → OCR (ABBYY) → Markdown
    └── file_hash_manager.py   # SQLite-хэши файлов
```

## Связанные проекты

- [../RAG System Web UI/README.md](../RAG%20System%20Web%20UI/README.md) — веб-интерфейс: чат, админка, мастер служебных записок; работает поверх этого API.
- [../generate_memos.py](../generate_memos.py) — массовая генерация служебных записок по шаблону `mmo.dotx` в каталог `../out` (заполнение полей и footer через Word COM).