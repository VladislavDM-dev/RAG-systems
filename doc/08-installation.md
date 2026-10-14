# 08. Установка, запуск и конфигурация

> Требуется **Windows** (Word COM для `.doc`/страниц `.docx`; сгенерированный корпус `out/` тоже создаётся через Word COM). Без Word тесты парсеров и перегенерация корпуса невозможны.

## 8.1 Предварительные условия

1. **Python 3.12** (локально проекты работают на системном Python 3.12, PowerShell 5.1).
2. **Внешний бэкенд инференса** (хотя бы один):
   - **Ollama** — нативный API, по умолчанию `http://127.0.0.1:11434`, или
   - **LM Studio** — запустить локальный сервер (Developer → Start server), URL `http://127.0.0.1:1234/v1`.
   - Необходимые модели: **LLM** (для ядра локально `qwen3.8-4b-distill` / дефолт `qwen3:4b`), **эмбеддинги** (`text-embedding-nomic-embed-text-v1.5` / `nomic-embed-text-v2-moe:latest`), опц. модель ключевых слов.
3. **Word** (для COM: `.doc` → `.docx`, подсчёт страниц `.docx`) — обязателен при индексации этих форматов.
4. **ABBYY FineReader 15** (`C:\Program Files (x86)\ABBYY FineReader 15\FineCmd.exe`) — для OCR `.pdf`. Без него PDF-файлы обрабатываются с ошибкой.

## 8.2 Создание окружений

Каждый проект — **отдельный venv** (системный Python не подходит — нет зависимостей):

```powershell
# Ядро
python -m venv "C:\Scripts\RAG systems\RAG System\.venv"
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -m pip install -r "C:\Scripts\RAG systems\RAG System\requirements.txt"

# Web UI
python -m venv "C:\Scripts\RAG systems\RAG System Web UI\.venv"
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -m pip install -r "C:\Scripts\RAG systems\RAG System Web UI\requirements.txt"
```

> ⚠️ `requirements.txt` Web UI **неполный**: в нём нет `python-docx`, хотя `app.py`/`memo_docx.py` его импортируют. При развёртывании на чистом venv доустановите: `pip install python-docx`.

## 8.3 Настройка ядра

Файл `RAG System/rag_engine/settings.json` (в .gitignore, создаётся/правится автоматически). Пример рабочей конфигурации:

```json
{
    "api_key": "",
    "chunk_overlap": 50,
    "chunk_size": 256,
    "context_window": 32768,
    "embedding_dim": 768,
    "llm": "qwen3.8-4b-distill",
    "llm_embed": "text-embedding-nomic-embed-text-v1.5",
    "llm_keywords": "qwen3.8-4b-distill",
    "page_limit": 10,
    "provider": "lmstudio",
    "similarity_top_k": 10,
    "size_limit_mb": 5,
    "sync_folders": ["C:\\Scripts\\RAG systems\\out"],
    "url": "http://127.0.0.1:1234/v1"
}
```

Всё это можно менять и через админку Web UI (или напрямую `PATCH /rag/config`).

> Смена `llm_embed`/`chunk_size`/`embedding_dim` пересоздаёт индекс (reset + персинхронизация).

## 8.4 Запуск (порядок важен)

Сначала ядро (порт 11455, префикс `/rag`), потом Web UI:

```powershell
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -X utf8 app.py
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -X utf8 app.py
```

- `-X utf8` обязателен у обоих (иначе ломается кириллица в `.docx`).
- Web UI: порт по умолчанию 80 (нужен админ); задайте `$env:PORT="5000"`, чтобы запустить без прав.
- При первом запуске Web UI создаёт пользователя `admin` (пароль по умолчанию `admin123`).

Доступ:
- Чат: `http://127.0.0.1/`
- Админка: `http://127.0.0.1/admin`
- RAG API: `http://127.0.0.1:11455/rag`

## 8.5 Переменные окружения

### Ядро
Переменных окружения у ядра нет — только `rag_engine/settings.json`.

### Web UI

| Переменная | По умолчанию | Примечание |
|---|---|---|
| `RAG_API_URL` | `http://127.0.0.1:11455/rag` | адрес API ядра |
| `PORT` | `80` | порт Web UI |
| `DATABASE_URL` | `sqlite:///<BASE_DIR>/data/app.db` | SQLAlchemy URL (в frozen — рядом с exe) |
| `SECRET_KEY` | — | если задан — используется напрямую |
| `SECRET_KEY_FILE` | `data/secret_key` | путь к файлу секрета (создаётся при необходимости) |
| `OPEN_REGISTRATION` | `true` | разрешить саморегистрацию `true/false` |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | пароль seed-админа |
| `MEMO_TEMPLATE_DIR` | `<корень репо>/docx_templates` | каталог `mmo.dotx` (в frozen — `_internal/docx_templates`) |

Пример запуска Web UI на порту 5000, ядро на удалённой машине:

```powershell
$env:RAG_API_URL = "http://172.30.99.77:11455/rag"
$env:PORT = "5000"
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -X utf8 app.py
```

## 8.6 Перегенерация корпуса `out/` (для тестов ядра)

Корпус `out/` — сгенерированный набор служебок из шаблона `mmo.dotx` (подставляются разные темы, footer с номерами). Нужен только тестам ядра (`test_parse_all_docx_files` требует ≥49 файлов).

```powershell
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -X utf8 generate_memos.py
```

Требует Word COM (WinWord). Папка `out/` в `.gitignore` и в коммиты не попадает.

## 8.7 Типичные ошибки запуска

- **Порт 80 занят / нет прав** → используйте `PORT=5000`.
- **`tiktoken ValueError: Unknown encoding cl100k_base`** в frozen-сборке → в `build.spec` должны быть `collect_data_files("tiktoken_ext")` (см. документ 10).
- **Web UI запустился, но чат пишет «Бэкенд недоступен»** → не запущено ядро/бэкенд; проверьте `RAG_API_URL`, статус админки.
- **Кириллица в .docx ломается** → у обоих приложений запуск без `-X utf8`.