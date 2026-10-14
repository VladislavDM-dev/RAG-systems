# 09. Тестирование

## 9.1 Запуск

```powershell
# Ядро — из каталога "RAG System"
& "RAG System\.venv\Scripts\python.exe" -m pytest

# Web UI — из каталога "RAG System Web UI"
& "RAG System Web UI\.venv\Scripts\python.exe" -m pytest
```

Опция `-X utf8` рекомендуется (кириллица в исключениях/выводе). `pytest.ini` ядра: `testpaths = tests`, `addopts = -q`.

## 9.2 Тесты ядра (`RAG System/tests/`)

### `conftest.py` — важное поведение
- Фикстура `pin_settings` (session) **перезаписывает `rag_engine/settings.json` на дефолты кода** на время прогона и **восстанавливает исходное** содержимое после. Не удивляйтесь «пропавшей» локальной конфигурации во время тестов.
- `client` (session): копирует cwd во временную папку до импорта `app`, а затем удаляет её — `.cache` не засоряет проект. После прогона cwd восстанавливается.

### Покрытие

| Файл | Что проверяет |
|---|---|
| `test_api.py` | health/info/engine_status/config (get/patch: валидные поля, невалидные, bad provider), folders roundtrip, provider set/switch (подстановка DEFAULT_URLS, autofix моделей, отключение autofix при недоступном бэкенде), models, parse (нет пути / файл не найден / реальный файл из `out/`), index_status, parse_stream, agent_stream (нет prompt / нет индекса / эмит событий), memos (нет prompt / без индекса / documents / stream reasoning) |
| `test_config.py` | дефолты, update → changed, отсутствие изменений, save/load roundtrip, to_dict |
| `test_file_hash_manager.py` | иниц. БД, save/get, get по отсутствующему, overwrite, remove, get_all_paths/hashes, close (освобождение файла) |
| `test_parsers.py` | `out/` содержит `.docx`, `test_parse_all_docx_files` (<ins>парсит ВСЕ `.docx` из `../out` через Word COM — медленный, требует ≥49 файлов</ins>), метаданные, отсутствующий файл |
| `test_providers.py` | фабрика провайдеров (ollama, lmstudio, алиасы, case-insensitive, unknown → ProviderError), DEFAULT_URLS, is_available(false), capabilities LM Studio (embedding по имени) |

## 9.3 Тесты Web UI (`RAG System Web UI/tests/`)

### `conftest.py`
- **До импорта `app`** выставляет: временную SQLite (`DATABASE_URL`), тестовый `SECRET_KEY`, недостижимый `RAG_API_URL`.
- `FakeRAG(RAGClient)` — стаб всех методов (health/info/engine_status/get_config/list_models/get_folders/parse_file/memos + schedule: get/add/update/delete с той же валидацией, что на ядре), без сети. Подставляется в `app.rag` в каждом тесте.
- `client` — свежая БД (`drop_all`/`create_all`), seed `admin/admin123`.
- `logged_client` — логин через форму с CSRF-токеном.
- ⚠️ Из реальных файлов используется только `docx_templates/mmo.dotx` (через `/api/memo/template`).

### Покрытие (`test_app.py`)
- Аутентификация: страница логина, редирект анонима, неверный пароль, bad CSRF, logout.
- Чат: страница `/`, CRUD диалогов, roundtrip сообщений, CRUD избранного.
- Мастер: `memo_template`, `memo_state` save/load/clear, требование объекта.
- Записки (`/memos`): рендер документов, стриминг reasoning, пусто, ошибка, авто-детекция (без команды), НЕ срабатывает для обычных вопросов и при явном `system_prompt`.
- Reasoning: стриминг и склейка в `done`.
- Админка: требует admin, users create/delete, запрет удаления себя, info, status.
- Расписание: админ-CRUD через прокси ядра, валидация (дни, HH:MM, текст), 404 для несуществующего id, блокировка стрима/статуса для не-админа, inactive не применяется.
- Уведомления/обратная связь/пароль: создание и dismiss уведомления, feedback ≤2000, смена пароля (неверный текущий → 400).
- `detect_memos_topic`: маркеры, игнорирование «вопросов о сути», обычные запросы.

## 9.4 JS: проверка синтаксиса и headless

JS не покрыт pytest. Проверки вручную:

```powershell
node --check static\js\chat.js
node --check static\js\memo.js
node --check static\js\utils.js
node --check static\js\admin.js
node --check static\js\history.js
node --check static\js\sync.js
node --check static\js\app.js
```

Полный обход UI — headless через puppeteer-core + системный Chrome (скрипты лежат вне репозитория; используются при функциональной проверке). При изменениях JS не забывайте бампать `MEMO_JS_VERSION` в `config.py` Web UI, иначе браузер отдаст закешированный файл.

## 9.5 Особенности и ограничения

- CI без Windows+Word невозможен: `test_parse_all_docx_files`, `doc_parser`, подсчёт страниц через COM требуют установленного Word.
- `out/` (корпус) после перегенерации ломает `test_parse_*` с `#20-`-файлом, т.к. пути/содержимое меняются — тесты зависят от актуального корпуса.
- Тесты ядра конфигурируют свой settings.json и не должны трогать прод-настройки; после прогона конфиг восстанавливается автоматически.