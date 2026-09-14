# AGENTS.md

Репозиторий из двух независимых Python-проектов: ядро RAG (`RAG System`) и веб-интерфейс (`RAG System Web UI`). У каждого **свой `.venv`** — системный Python не подходит (нет зависимостей). PowerShell 5.1: вызов `.py`/`.venv` требует `& "путь"` и запуска с `-X utf8`.

## Запуск (порядок важен)

Сначала ядро (порт 11455, префикс `/rag`), потом веб-интерфейс (порт 80 проксирует `/rag/*` на ядро):

```powershell
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -X utf8 app.py
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -X utf8 app.py
```

- `-X utf8` обязателен у обоих приложений и у `generate_memos.py` — иначе ломается кириллица в `.docx`.
- Web UI: порт — env `PORT` (по умолч. 80, нужен админ), адрес ядра — `RAG_API_URL` (по умолч. `http://127.0.0.1:11455/rag`). Есть вход: логин `admin`, пароль по умолчанию `admin123`.
- Ядро читает `rag_engine/settings.json` (в gitignore, локальная конфигурация): сейчас `provider=lmstudio`, `url=http://127.0.0.1:1234/v1`, `llm_embed=text-embedding-nomic-embed-text-v1.5`.

## Ключевые факты

- **Мастер записки (`/create <тема>`)** берёт варианты тела из готовых `.docx` в `out/` (НЕ генерирует через LLM). Исполнитель/телефон читаются из колонтитулов (footer). Путь к корпусу: Web UI `app.py:522` (`_MEMO_FOLDER = ../out`, абсолютный).
- **Web UI RAM-кэш**: `/api/memos` открывает ВСЕ `.docx` из `out/` и держит полный текст в памяти 10 сек (TTL `_MEMOS_CACHE_TTL`, app.py:524). При 2000+ документах это сотни МБ — не усугубляйте (не добавляйте постоянных копий текста в память без необходимости).
- **Шаблон `docx_templates/mmo.dotx`** — бинарный, но в git. Поля шаблона определяются из самого файла (`memo_docx.discover_template_fields`). Правки Word меняют байты даже при «невидимых» изменениях — перед правками проверяйте соответствие плейсхолдеров (`{{ ... }}`), а git-diff больших бинарных изменений не доверяйте.
- **Бампить `MEMO_JS_VERSION`** в Web UI `app.py:26` при каждой правке `static/js/memo.js` или `main.js`, иначе браузер отдаст закешированную версию (версия вставляется в `index.html` как `?v=...`).
- **`requirements.txt` Web UI неполный**: `app.py` и `memo_docx.py` импортируют `docx` (python-docx), но в requirements его нет — установлен вручную в `.venv`. При развёртывании на чистом venv доустановите `python-docx`.
- `out/` — сгенерированный корпус, в gitignore. Тесты и Web UI зависят от его наличия. Перегенерить: `& "RAG System\.venv\Scripts\python.exe" -X utf8 generate_memos.py` (нужен Word COM).

## Windows / COM-ограничения

- `.doc` и подсчёт страниц `.docx` идут через Word COM (`win32com`); `.pdf` — через ABBYY FineReader 15 (жёсткий путь `C:\Program Files (x86)\ABBYY FineReader 15\FineCmd.exe`).
- Все обращения к Word COM сериализованы общим `_WORD_LOCK` — **не вносите параллельный Word** (Word зависает). Не создавайте спавн нескольких Word.Application.
- Всё это тестируется только на Windows с установленным Word; CI без Word невозможен.

## Тесты

```powershell
& "RAG System\.venv\Scripts\python.exe" -m pytest   # из каталога RAG System
& "RAG System Web UI\.venv\Scripts\python.exe" -m pytest   # из каталога RAG System Web UI
```

- Тесты ядра: conftest **перезаписывает `settings.json` на дефолты на время прогона и восстанавливает** после — не удивляйтесь «пропавшей» конфигурации во время тестов.
- `test_parse_all_docx_files` парсит ВСЕ `.docx` из `../out` через Word COM — медленный. Требует ≥49 файлов в `out/`.
- Тесты Web UI тоже читают реальные `.docx` (`out/`, `docx_templates/mmo.dotx`).
- JS мастера (memo.js/main.js) тестами не покрыт — проверяйте headless через puppeteer-core скрипты + системный Chrome.

## Сборка (PyInstaller)

- Spec-файлы: `RAG System/build.spec` (ядро), `RAG System Web UI/build.spec` (Web UI). Скрипт для обоих — `build_all.ps1` в корне (ставит PyInstaller в venv проекта при первом запуске). Результат — onedir-EXE в `dist/<имя>/`.
- Ядро: `datas` для `tiktoken_ext` (иначе `ValueError: Unknown encoding cl100k_base`) и `hook_runtime.py` (UTF-8 для stdout/stderr, т.к. exe не наследует `-X utf8`).
- В frozen-режиме конфиг пишется рядом с exe: `settings.json` и `.cache/` (`config.config_dir()`, `RAGEngine.cache_dir`). Дефолты конфликта — каталог корпуса Web UI: env `MEMO_CORPUS_DIR` (по умолч. `<exe_dir>/../out`), шаблон — env `MEMO_TEMPLATE_DIR` (`docx_templates/mmо.dotx`).
- Запуск тестов после правок путей ядра: конфиг не ломается (тесты конфигурируют свой settings.json), но `test_parse_*` с `#20-`-файлом из `out/` падают, если корпус перегенерирован.

## Git

- Сообщения коммитов на английском, префиксы `feat:`/`fix:` (см. `git log --oneline`). Не форсить и не амендить без явного запроса.
- Никогда не коммитить: `RAG System Web UI/data/`, `users.json`, `rag_engine/settings.json` (секреты/локальные пути), `out/`, `.cache/`, `.venv/`.