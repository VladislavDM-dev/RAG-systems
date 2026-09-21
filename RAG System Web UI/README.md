# RAG System Web UI

Веб-интерфейс для сервиса **RAG System** (Flask API на порту `11455`, префикс `/rag`):
чат с базой знаний, админ-панель и **мастер генерации служебных записок**.

Всё работает **только через RAG API**: приложение не читает локальный корпус
`out/` и не держит кэшей документов. Чат по умолчанию ходит в stream агента RAG,
поиск записок — RAG-промптом (команда `/memos`), варианты тела записки —
тоже через RAG.

## Возможности

- **Чат**: RAG-агент через SSE (`/api/chat/stream`), источники, команды
  `/create <тема>` и `/memos <тема>`, история диалогов и избранное на сервере.
- **Авторизация**: вход/выход, регистрация (если `OPEN_REGISTRATION=true`),
  роли `admin`/`user`. По умолчанию создаётся `admin/admin123`.
- **Мастер служебной записки** (команда `/create <тема>`):
  - варианты тела генерирует RAG по системному промпту (`SYSTEM_PROMPT_MEMO_VARIANTS`),
    а не из готовых `.docx`;
  - связанные пары полей: «Кому должность ↔ ФИО»,
    «Подписывающее лицо должность ↔ ФИО», «исполнитель ↔ телефон» — выбор варианта
    автоподтягивает парный;
  - у полей — по 5–6 вариантов, поле **«Дата»** заполняется текущей датой;
  - пошаговый предпросмотр и скачивание готового `.docx` через `/api/memo/docx`;
  - структуру полей даёт сервер: `/api/memo/template` (из `docx_templates/mmo.dotx`).
- **Админка** (`/admin`): статус RAG, модели, папки, синхронизация, управление
  пользователями.
- **Восстановление сессии**: незавершённый мастер записки (localStorage) и последний
  диалог возвращаются после перезагрузки страницы.

## Структура

```
RAG System Web UI/
├── app.py            # Flask-приложение, create_app(), маршрут / (чат)
├── config.py         # Настройки из env, системные промпты, MEMO_JS_VERSION
├── extensions.py     # db, csrf, login_manager
├── models.py         # User, Conversation, Message, Favorite
├── auth.py           # /login, /register, /logout
├── chat.py           # /api/chat/stream, conversations, messages, favorites, /api/status
├── memo.py           # /api/memo/template, /api/memo/docx, админ-роуты шаблона
├── admin.py          # /admin и /api/admin/* (только для admin)
├── api_client.py     # Клиент к RAG API (прокси + SSE)
├── memo_docx.py      # Сборка .docx по шаблону; обход body + header/footer секций
├── docx_templates/mmo.dotx
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── chat/index.html
│   ├── admin/index.html
│   └── auth/{login,register}.html
├── static/
│   ├── css/          # bootstrap, bootstrap-icons, style.css
│   └── js/           # utils, history, chat, sync, memo, app, admin, dompurify.min.js
├── data/             # SQLite (app.db), secret_key (исключены из git)
└── tests/            # pytest-тесты (RAG API заглушён)
```

## Запуск

Порядок важен: сначала ядро RAG (порт 11455, префикс `/rag`), затем веб-интерфейс:

```powershell
& "C:\Scripts\RAG systems\RAG System\.venv\Scripts\python.exe" -X utf8 app.py
& "C:\Scripts\RAG systems\RAG System Web UI\.venv\Scripts\python.exe" -X utf8 app.py
```

> `-X utf8` обязателен — иначе ломается кириллица в формировании `.docx`.

Страницы:

- `http://127.0.0.1/` — чат (вход, мастер записок, история).
- `http://127.0.0.1/admin` — админ-панель.

> Порт по умолчанию `80` требует прав администратора; сменить — env `PORT`.

## Настройка

| Переменная             | По умолчанию                 | Описание                              |
|------------------------|------------------------------|---------------------------------------|
| `RAG_API_URL`          | `http://127.0.0.1:11455/rag` | Базовый URL API RAG System            |
| `PORT`                 | `80`                         | Порт веб-интерфейса                   |
| `DATABASE_URL`         | `sqlite:///data/app.db`      | SQLAlchemy URL базы                   |
| `SECRET_KEY` / `SECRET_KEY_FILE` | — (авто-генерация)  | Ключ Flask; файл `data/secret_key`    |
| `OPEN_REGISTRATION`    | `true`                       | Разрешить регистрацию новых пользователей |
| `MEMO_TEMPLATE_DIR`    | `docx_templates`             | Каталог с `mmo.dotx` (важно для frozen) |

Пример:

```powershell
$env:RAG_API_URL = "http://172.30.99.77:11455/rag"
$env:PORT = "5000"
& ".venv\Scripts\python.exe" -X utf8 app.py
```

## Как это работает

Веб-интерфейс сам не индексирует документы — запросы чата и админки идут напрямую
в RAG API (через `api_client.py`, стриминговые эндпоинты — как SSE). История,
избранное, пользователи и генерация `.docx` хранятся в **самом веб-интерфейсе** (SQLite).

Эндпоинты приложения (`/api/...`):

| Путь                          | Описание                                     |
|-------------------------------|----------------------------------------------|
| `GET /api/status`             | Статус RAG-индекса (для поллинга синхронизации) |
| `POST /api/chat/stream`       | SSE-чат агента RAG                           |
| `POST /api/parse`             | Парсинг файла на бэкенде                     |
| `GET/POST/DELETE /api/conversations(/<id>)` | История диалогов                   |
| `GET/POST /api/messages`      | Сообщения диалога                            |
| `GET/POST/DELETE /api/favorites(/<id>)` | Избранные ответы                        |
| `GET /api/memo/template`      | Поля шаблона `mmo.dotx`                      |
| `POST /api/memo/docx`         | Сборка `.docx` по значениям полей            |
| `GET/POST/DELETE /api/admin/users(/<id>)` | Управление пользователями (admin)   |
| `POST /api/admin/memo/template/reload` | Перечитать шаблон с диска (admin)    |
| `POST /api/admin/memo/template` | Сохранить шаблон на диск (admin)          |

## Мастер служебной записки

1. В чате: `/create <тема>`.
2. RAG генерирует 5–6 вариантов тела по теме; исполнитель и телефон берутся из
   связки полей с вариантами.
3. Одно окно: выбор варианта тела (заполняет textarea) + все поля шапки.
   Поля «Дата» и «Номер» — ручные, остальные — из RAG или свои.
4. «Далее» → предпросмотр → «Скачать .docx и сохранить»: файл формируется через
   `memo_docx.py` по `docx_templates/mmo.dotx`.
5. Состояние мастера (`localStorage`) сохраняется на каждом действии — после
   перезагрузки страницы работа продолжается с того же места.

Версия клиентских скриптов задаётся в `config.py` (`MEMO_JS_VERSION`) и подставляется
в шаблоны как `?v=...` — обязательно обновляйте при правках JS, иначе браузер отдаст
закешированную версию.

## Тесты

```powershell
& ".venv\Scripts\python.exe" -X utf8 -m pytest
```

Тесты не обращаются к сети: `conftest.py` подменяет RAG-клиент заглушкой и ставит
временную SQLite-базу. Покрыты: вход/выход, CSRF, CRUD диалогов, сообщений и
избранного, шаблон мемо, админ-функции и права ролей.

Обновление JS-клиента проверяется `node --check` (Node не требуется для pytest).