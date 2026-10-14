# 04. API ядра RAG System (`/rag/*`)

Сервер: Flask на порту **11455**, все endpoints под префиксом **`/rag`**.
Формат ответов — JSON (`ensure_ascii=False` там, где используется `json.dumps`), стриминг — SSE (`text/event-stream`).

## 4.1 Health / metadata

### `GET /rag/health`
```json
{ "status": "ok" }
```

### `GET /rag/info`
```json
{
  "service": "RAG System",
  "engine": "IndexDocuments RAGEngine",
  "version": "26.10.13",
  "provider": "lmstudio",
  "initialized": true,
  "syncing": false,
  "document_count": 53,
  "status_backend": true
}
```

### `GET /rag/engine/status`
Полный статус движка:
```json
{
  "is_initialized": true,
  "is_syncing": false,
  "status": "Готово к работе",
  "progress": 100,
  "status_backend": true,
  "document_count": 53,
  "sync_files": [],
  "index_updated": "2026-09-22T10:15:00",
  "version": "26.09.22"
}
```

## 4.2 Чат / агентный стриминг

### `POST /rag/agent/stream` (SSE)

Тело (JSON):
| Поле | Тип | Обязательно | Примечание |
|---|---|---|---|
| `prompt` | str | да | Вопрос/промпт агента (либо `question`) |
| `system_prompt` | str | нет | системная инструкция (по умолчанию `DEFAULT_AGENT_SYSTEM_PROMPT`) |
| `top_k` | int | нет | фрагментов для ретрива (по умолчанию `similarity_top_k`) |
| `temperature` | float | нет | по умолчанию 0.98 |
| `exclude_node_ids` | list[str] | нет | node_id уже отданных фрагментов (постраничный обход) |

Ошибки до стрима: `400` (пустой prompt), `503` (индекс не готов — «Дождитесь завершения синхронизации»).

События SSE (`data: {json}\n\n`):

| type | Поля | Когда |
|---|---|---|
| `sources` | `data`: `[{file_name, file_path, node_id, score}]` | сразу после ретрива, до токенов |
| `reasoning` | `data` (delta) | «размышления» модели (thinking), порциями |
| `token` | `data` (delta) | текст ответа, порциями |
| `done` | `answer, reasoning, sources, prompt, tokens_in, tokens_out, elapsed` | финал |
| `error` | `data` | ошибка генерации/LLM |

Пример `done`:
```json
{
  "type": "done",
  "answer": "В ответе из документов …",
  "reasoning": "Мысли модели…",
  "sources": [{"file_name": "#297-….docx", "file_path": "C:\\…\\#297….docx", "node_id": "…", "score": 0.42}],
  "prompt": "…",
  "tokens_in": 1234,
  "tokens_out": 87,
  "elapsed": 3.15
}
```

## 4.3 Поиск служебных записок

### `POST /rag/memos`
Поиск **всех** записок по теме, в ответе — полный текст документов (собирается из docstore индекса, файлы повторно не парсятся).

Тело: `prompt` (обязательно), опц. `temperature` (по умолч. 0.0), `page_size` (50), `max_pages` (15).

Ответ `200`:
```json
{
  "ok": true,
  "total": 3,
  "pages": 1,
  "documents": [
    { "file_name": "#297-….docx", "file_path": "C:\\…\\#297….docx", "text": "полный текст…" }
  ]
}
```
Ошибки: `400` (нет prompt), `503` (идет синхронизация / индекс не готов), `500` (прочее).

### `POST /rag/memos/stream` (SSE)
То же, но постранично стримится `reasoning` батч-LLM:
- `reasoning` — размышления батча;
- `done`: `{documents, pages, prompt, tokens_in, tokens_out, elapsed}`;
- `error`.

## 4.4 Индексация

### `POST /rag/index`
Запуск синхронизации (фоновый поток). `?reset=true` — полный сброс кэша + пересинхронизация.
- `202`: `{status: "started", reset: false, message: "Синхронизация запущена"}`
- `200`: `{status: "already_syncing", ...}` — если уже идёт.

### `GET /rag/index/status`
```json
{
  "is_syncing": true,
  "status": "Обработано 12/50 файлов.",
  "progress": 29,
  "sync_files": [{"file": "…", "operation": "…"}],
  "initialized": false,
  "document_count": 12,
  "index_updated": "—"
}
```

### `GET /rag/index/stats`
```json
{ "document_count": 53, "index_updated": "2026-09-22T…", "status": "Готово к работе" }
```

## 4.5 Папки синхронизации

### `GET /rag/folders`
```json
{ "folders": ["C:\\Scripts\\RAG systems\\out"] }
```

### `POST /rag/folders`
`{ "folders": ["C:\\Docs"] }` → `{ "ok": true, "folders": [...] }`. `400` если не список.

## 4.6 Конфигурация

### `GET /rag/config`
Полный `Settings.to_dict()`: provider, context_window, chunk_size, chunk_overlap, similarity_top_k, page_limit, size_limit_mb, embedding_dim, llm, llm_embed, llm_keywords, url, api_key, sync_folders.

### `PATCH /rag/config`
Частичное обновление. Допустимые ключи: `provider, api_key, context_window, chunk_size, chunk_overlap, similarity_top_k, page_limit, size_limit_mb, embedding_dim, llm, llm_embed, llm_keywords, url`.

- `provider` допускает только `ollama | lmstudio` (иначе 400).
- Ответ: `{"ok": true, "changed": ["llm"], "config": {...}}`.
- Побочные эффекты: смена эмбеддинг-параметров → пересоздание индекса (`start_sync(is_remove=True)`); смена LLM-параметров/провайдера → пересборка моделей.

### `POST /rag/config/reset`
Сброс конфига к дефолтам + пересинхронизация:
```json
{ "ok": true, "config": {...} }
```

## 4.7 Провайдер и модели

### `GET /rag/provider`
```json
{
  "provider": "ollama",
  "status_backend": true,
  "models": { "all": [...], "thinking": [...], "embedding": [...] }
}
```

### `POST /rag/provider`
`{ "provider": "lmstudio" }` → `{"ok": true, "provider": "lmstudio", "config": {...}}`. `400` при недопустимом значении.

### `GET /rag/models`
Перепроверяет бэкенд, если он был недоступен (`refresh_backend_models`), и отдаёт то же, что `/rag/provider`.

## 4.8 Парсинг файлов (отладка)

### `POST /rag/parse`
`{ "file_path": "C:\\Docs\\file.docx" }`.
- `200`: `{"ok": true, "page_count": 5, "content": "…markdown…"}`
- `404`: файл не найден.
- `400`: нет file_path / неподдерживаемый формат (только `.doc/.docx/.pdf`).
- `500`: ошибка парсера.

### `POST /rag/parse/stream` (SSE)
Поабзацная выдача: `chunk {type, data}` → … → `done {type, page_count}`; `error` при сбое.

## 4.9 Расписание ограничений использования

Единый источник расписания запрета — **ядро** (`Settings.usage_restrictions` в `settings.json`). Web UI хранит расписание в SQLite больше не может — только проксирует эти endpoints. Логика: `rag_engine/schedule.py` (валидация, `applies_now` по локальному времени сервера ядра).

Ограничение: `{id, days:[0..6] (0=Пн), start_time "HH:MM", end_time "HH:MM", message, active}`. `start == end` — весь день; диапазон через полночь поддерживается.

### `GET /rag/schedule`
```json
{
  "server_time": "2026-10-13T22:40:00",
  "server_time_hm": "22:40",
  "weekday": 0,
  "restrictions": [
    { "id": 1, "days": [0,1,2,3,4], "start_time": "18:00", "end_time": "09:00",
      "message": "…", "active": true, "applies_now": true }
  ]
}
```

### `POST /rag/schedule`
`{days, start_time, end_time, message, active?}` → `200 {ok, …schedule_response}` (id назначает сервер). Ошибки валидации — `400 {error}`.

### `PUT /rag/schedule/<id>`
Частичное обновление (любые поля из `days/start_time/end_time/message/active`). `404` если id нет.

### `DELETE /rag/schedule/<id>`
`200 {ok, …}`. `404` если id нет.

## 4.10 Итоговая таблица

| Метод | Путь | Формат | Назначение |
|---|---|---|---|
| GET | `/rag/health` | JSON | проверка доступности |
| GET | `/rag/info` | JSON | метаданные/версия/статус |
| GET | `/rag/engine/status` | JSON | полный статус движка |
| POST | `/rag/agent/stream` | SSE | чат/агентный ответ |
| POST | `/rag/memos` | JSON | все записки по теме |
| POST | `/rag/memos/stream` | SSE | то же с reasoning |
| POST | `/rag/index` | JSON | запуск синхронизации (`?reset=true`) |
| GET | `/rag/index/status` | JSON | статус синхронизации |
| GET | `/rag/index/stats` | JSON | статистика |
| GET/POST | `/rag/folders` | JSON | папки синхронизации |
| GET/PATCH | `/rag/config` | JSON | конфигурация |
| POST | `/rag/config/reset` | JSON | сброс конфига |
| GET/POST | `/rag/provider` | JSON | провайдер |
| GET | `/rag/models` | JSON | модели бэкенда |
| POST | `/rag/parse` | JSON | парсинг файла |
| POST | `/rag/parse/stream` | SSE | парсинг поабзацно |
| GET/POST | `/rag/schedule` | JSON | расписание запрета: список / добавить |
| PUT/DELETE | `/rag/schedule/<id>` | JSON | обновить / удалить ограничение |