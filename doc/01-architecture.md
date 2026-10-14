# 01. Архитектура

## 1.1 Обзор

Система — классический RAG-стек (Retrieval-Augmented Generation): документы индексируются в векторную базу, по запросу извлекаются релевантные фрагменты, и LLM формирует ответ с опорой только на них.

```mermaid
flowchart LR
    subgraph Client["Клиент"]
        B["Браузер (SPA)\nchat/index.html + JS"]
    end

    subgraph WebUI["RAG System Web UI (Flask, :80/:PORT)"]
        AUTH["auth: /login /register"]
        CHAT["chat: / /api/chat/stream\nмастер /create, /memos"]
        MEMO["memo: /api/memo/template\n/api/memo/docx"]
        ADM["admin: /admin /api/admin/*"]
        DB_[(SQLite:\ndata/app.db)]
    end

    subgraph Core["RAG System (Flask, :11455, /rag)"]
        API["app.py\nREST + SSE"]
        ENG["RAGEngine\nLlamaIndex"]
        FAISS[("FAISS\nиндекс + docstore")]
        PARS["Парсеры\n.docx / .doc / .pdf"]
    end

    subgraph Backend["Инференс"]
        OLL["Ollama\n:11434"]
        LMS["LM Studio\n:1234/v1"]
    end

    B -->|HTTP/SSE| WebUI
    WebUI -->|RAGClient\nhttp://127.0.0.1:11455/rag| API
    API --> ENG
    ENG --> FAISS
    ENG -->|embed / llm| Backend
    ENG --> PARS
    PARS -->|"файлы из sync_folders"| DOCS["Корпус документов\n(напр. C:\Scripts\RAG systems\out)"]

    ADM --> DB_
    CHAT --> DB_
```

**Ключевое правило:** Web UI **не** читает корпус `out/` напрямую и не держит кэши документов. Вся логика индексации, поиска и генерации живёт в ядре; Web UI лишь проксирует запросы через `RAGClient` (`api_client.py`) и стримит SSE в браузер.

## 1.2 Запуск и порядок

Сначала ядро, потом Web UI (порт 80 проксирует `/rag/*` на ядро):

```powershell
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -X utf8 app.py
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -X utf8 app.py
```

- `-X utf8` обязателен у обоих приложений (иначе ломается кириллица в `.docx`).
- Адрес ядра Web UI берёт из `RAG_API_URL` (по умолчанию `http://127.0.0.1:11455/rag`).
- Порт Web UI — env `PORT` (по умолчанию 80, требует прав администратора).
- Web UI при первом запуске создаёт `data/app.db` (SQLite) и пользователя `admin` с паролем из `DEFAULT_ADMIN_PASSWORD` (по умолчанию `admin123`).

## 1.3 Поток запроса в чате (SSE)

```mermaid
sequenceDiagram
    participant B as Браузер (chat.js)
    participant W as Web UI (/api/chat/stream)
    participant C as Ядро (/rag/agent/stream)
    participant I as FAISS index
    participant L as LLM (Ollama/LM Studio)

    B->>W: POST /api/chat/stream {prompt, system_prompt, temperature}
    W->>C: POST /rag/agent/stream (SSE)
    C->>C: проверки: is_syncing / is_initialized
    C->>I: retriever.retrieve(prompt) (top_k + exclude)
    I-->>C: nodes (с score)
    C-->>W: event: sources [{file_name, file_path, node_id, score}]
    C->>L: llm.stream_chat([промпт с контекстом])
    loop токены
        L-->>C: ChunkResponse (delta / thinking_delta)
        C-->>W: event: token | reasoning
    end
    C-->>W: event: done {answer, reasoning, sources, tokens_in, tokens_out, elapsed}
    W-->>B: SSE "data: {json}\n\n"
    B->>B: рендер markdown (marked + DOMPurify), метрики, источники
```

События SSE: `sources`, `reasoning` (thinking), `token`, `done`, `error`.

## 1.4 Поток индексации (фоновый поток ядра)

```mermaid
flowchart TD
    A["RAGEngine.initialize()"] --> B["__init_backend(): сборка LlamaSettings.llm / embed_model"]
    B --> C["__check_backend(): list_models, capabilities"]
    C --> D["thread: sync_index()"]
    D --> E{"Загрузить существующий\nFAISS-кэш (.cache/faiss_index)?"}
    E -->|есть| F["load_index_from_storage"]
    E -->|нет| G["Новый FaissVectorStore + persist (create)"]
    F --> H["_scan_documents(): обход sync_folders"]
    G --> H
    H --> I{"Изменения файлов?\n(file_hashes.db, MD5)"}
    I -->|нет| J["status: Готово к работе"]
    I -->|да| K["для каждого файла:\n_load_document → парсер"]
    K --> L["page_count sanity (0 < p ≤ page_limit) и size ≤ size_limit_mb"]
    L --> M["node_parser.get_nodes_from_documents → чанки"]
    M --> N["index.insert_nodes(nodes)"]
    N --> O["storage_context.persist(FAISS) + file_hash_db.save"]
    O --> J
```

Особенности:

- Обработка файлов **строго последовательная** (`for rel_path in new_or_modified`) — параллельные `insert_nodes` + `persist` в один FAISS-файл зависают/портят индекс.
- Инкрементальность по MD5-хэшу (таблица `file_hashes` в SQLite `.cache/file_hashes.db`).
- `reset=true` (`POST /rag/index?reset=true`) — очистка кэша и полная пересинхронизация.
- В frozen-режиме `.cache` создаётся рядом с exe (`Path(sys.executable).parent/.cache`).

## 1.5 Поток поиска записок (`/memos`)

Поиск **всех** служебных записок по теме с полным текстом. Использует постраничный обход индекса без повторов:

```mermaid
flowchart LR
    A["prompt по теме"] --> B["Извлечь корни слов темы\n(_memo_topic_words)"]
    B --> C["Гибридный отбор кандидатов"]
    C --> D1["Имя-фильтр: файлы, в названии которых есть корни\n(идут первыми, полными чанками)"]
    C --> D2["Семантический ретрив: retriever.retrieve(prompt)\n(доки по смыслу, не отражённые в имени)"]
    D1 --> E["candidate_pairs: [(file_path, node)]"]
    D2 --> E
    E --> F{"for page in 1..max_pages"}
    F -->|батч page_size чанков| G["Батч-LLM (stream_chat)\nс системным промптом _MEMO_BATCH_SYSTEM_PROMPT"]
    G --> H["reasoning стримится пользователю"]
    G --> I["Парсинг ответа: строки 'ПУТЬ: <путь>'"]
    I --> J{"В батче есть новые пути?"}
    J -->|да| K["добавить в found_paths, перейти к след. батчу"]
    J -->|"нет / 'НОВЫХ ЗАПИСОК НЕТ'"| L["Завершить"]
    L --> M["Сборка полного текста из docstore\n(_assemble_document_text по start_char_idx)"]
    M --> N["done: {documents, pages, tokens_in/out, elapsed}"]
```

Ключевые параметры: `page_size=50`, `max_pages=15`. Повторы исключаются через `node_ids` (множество `seen_ids`), а для постраничности используется подход с `exclude_node_ids` (см. `_ExcludeNodeIdsPostprocessor`).

## 1.6 Схема БД Web UI

```mermaid
erDiagram
    users ||--o{ conversations : "has"
    users ||--o{ favorites : "has"
    users ||--o{ memo_states : "has"
    conversations ||--o{ messages : "has"

    users {
        int id PK
        string username "unique, 3-32"
        string password_hash
        string role "admin | user"
        datetime created_at
        bool is_active
    }
    conversations {
        int id PK
        int user_id FK
        string title
        datetime created_at
        datetime updated_at
    }
    messages {
        int id PK
        int conversation_id FK
        string role "user | bot"
        text content
        text sources_json
        text memo_data_json
        datetime created_at
    }
    favorites {
        int id PK
        int user_id FK
        string title
        text content
        text sources_json
        text memo_data_json
        datetime created_at
    }
    memo_states {
        int id PK
        int user_id FK
        text state_json
        datetime updated_at
    }
```

## 1.7 Развёртывание

```mermaid
flowchart LR
    subgraph Dev["Разработка (.py)"]
        PY1["python -X utf8 app.py\n(ядро :11455)"] --> PY2["python -X utf8 app.py\n(Web UI :80 или :PORT)"]
    end

    subgraph Prod["Frozen (PyInstaller onedir)"]
        E1["dist/RAG System/RAG System.exe"] --> E2["dist/RAG System Web UI/RAG System Web UI.exe"]
    end

    subgraph Data["Данные"]
        S1["rag_engine/settings.json\nрядом с exe или модулем"]
        S2["data/app.db + data/secret_key\nрядом с exe (не в _internal)"]
        S3["_internal/docx_templates/mmo.dotx\n(зашит в сборку Web UI)"]
        S4[".cache/ (FAISS + file_hashes.db)\nрядом с exe ядра"]
    end
```

Особенности frozen-режима:

- Ядро: `config_dir()` → рядом с exe (settings.json), `.cache` → рядом с exe.
- Web UI: `hook_runtime.py` выставляет `MEMO_TEMPLATE_DIR=<exe_dir>/_internal/docx_templates`, `DATABASE_URL=sqlite:///<exe_dir>/data/app.db`, `SECRET_KEY_FILE=<exe_dir>/data/secret_key`.
- Не бандлится `out/` (корпус), `data/`, настройки — всё создаётся при первом запуске.

## 1.8 Ограничение: Word COM

Все обращения к Word COM (конвертация `.doc`, подсчёт страниц `.docx`, генерация корпуса) **сериализованы** общим локом `_WORD_LOCK` в `docx_parser.py`. Параллельные `Dispatch("Word.Application")` из нескольких потоков заставляют Word зависать, поэтому нельзя добавлять параллельный Word-код. Тестируется только на Windows с установленным Word (CI без Word невозможен).