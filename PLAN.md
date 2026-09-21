# RAG System Web UI — Новое приложение

## Краткое описание

Полная переработка Web UI на Flask + SQLite. Заменяет текущий `RAG System Web UI` на месте. Работает через API RAG System (порт 11455). Русскоязычный, десктоп-фокус, 2 роли (admin/user).

---

## 1. Архитектура

```
RAG System Web UI/           ← замена текущего каталога
├── app.py                   ← точка входа, Flask-приложение
├── config.py                ← конфигурация (env, defaults)
├── models.py                ← SQLAlchemy-модели
├── auth.py                   ← Blueprint: логин, регистрация, сессия
├── admin.py                  ← Blueprint: админ-панель
├── chat.py                   ← Blueprint: чат, SSE-стриминг, история
├── memo.py                   ← Blueprint: мастер создания мемо
├── api_client.py             ← обёртка над RAG System API
├── extensions.py             ← инициализация расширений (db, login_manager)
├── requirements.txt
├── build.spec                ← PyInstaller spec (замена текущего)
├── hook_runtime.py
├── templates/
│   ├── base.html             ← базовый layout (navbar, scripts, стили)
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── chat/
│   │   └── index.html        ← чат + история + мемо-мастер
│   ├── admin/
│   │   └── index.html        ← админ-панель (настройки, пользователи, шаблон)
│   └── components/
│       ├── _sync_overlay.html
│       ├── _history_panel.html
│       ├── _memo_wizard.html
│       └── _file_modal.html
├── static/
│   ├── css/
│   │   ├── style.css         ← кастомные стили
│   │   ├── bootstrap.min.css
│   │   └── bootstrap-icons.css
│   ├── js/
│   │   ├── app.js            ← точка входа, инициализация модулей
│   │   ├── chat.js           ← логика чата, SSE-стриминг
│   │   ├── history.js        ← управление историей (пагинация!)
│   │   ├── memo.js           ← мастер мемо
│   │   ├── admin.js          ← логика админ-панели
│   │   ├── sync.js           ← мониторинг синхронизации
│   │   └── utils.js          ← общие утилиты (fetch, SSE, markdown)
│   └── img/
│       └── logo.svg
├── data/                     ← SQLite + автосоздание
│   └── app.db
└── out/                      ← симлинк/путь к корпусу мемо
```

### Ключевые архитектурные решения

| Аспект | Решение |
|--------|---------|
| ORM | **SQLAlchemy** (через Flask-SQLAlchemy) |
| Миграции | **Flask-Migrate** (Alembic) — начальная миграция при первом запуске |
| Аутентификация | **Flask-Login** (session-based, CSRF через Flask-WTF) |
| Пароли | **werkzeug.security** (scrypt/pbkdf2, **никогда** plaintext) |
| SSE | Flask-Response с `text/event-stream` (как сейчас, через прокси к RAG core) |
| Кеширование мемо | **Нет RAM-кэша** — читаем на запрос, пагинация |
| Проксирование | requests → RAG API (не catch-all, только нужные эндпоинты) |

---

## 2. Модель данных (SQLAlchemy)

### Таблица `users`
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='user')  # 'admin' | 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password): ...
    def check_password(self, password): ...
```

### Таблица `conversations`
```python
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')
```

### Таблица `messages`
```python
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    role = db.Column(db.String(8), nullable=False)  # 'user' | 'bot'
    content = db.Column(db.Text, nullable=False)
    sources_json = db.Column(db.Text)  # JSON: [{file_name, file_path, score}]
    memo_data_json = db.Column(db.Text)  # JSON: данные мемо (для ботовых ответов с мемо)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Таблица `favorites` (избранное)
```python
class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False)
    content = db.Column(db.Text, nullable=False)
    sources_json = db.Column(db.Text)
    memo_data_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Преимущества перед текущей системой
- **Пагинация**: `Conversation.messages` — `lazy='dynamic'`, подгрузка по 50 сообщений
- **Индексация**: индексы на `user_id`, `conversation_id`, `created_at` — быстрые запросы
- **Каскадное удаление**: при удалении пользователя удаляются все его данные
- **Нет RAM-кэша мемо**: каждый запрос к `out/*.docx` — отдельное чтение с диска (с кешем мемо-файлов в `memo_docx.py` по mtime)

---

## 3. API-клиент (`api_client.py`)

Инкапсулирует все обращения к RAG System. Единая точка входа, timeout, retry, обработка ошибок.

```python
class RAGClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    # --- Инфраструктура ---
    def health(self) -> dict: ...
    def info(self) -> dict: ...
    def engine_status(self) -> dict: ...
    def index_status(self) -> dict: ...
    def index_stats(self) -> dict: ...

    # --- Управление индексом ---
    def trigger_sync(self, reset: bool = False) -> dict: ...

    # --- Конфигурация ---
    def get_config(self) -> dict: ...
    def patch_config(self, **kwargs) -> dict: ...
    def reset_config(self) -> dict: ...

    # --- Модели и провайдеры ---
    def list_models(self) -> dict: ...
    def get_provider(self) -> dict: ...
    def set_provider(self, provider: str) -> dict: ...

    # --- Папки ---
    def get_folders(self) -> list: ...
    def set_folders(self, folders: list) -> dict: ...

    # --- Чат (SSE) ---
    def stream_chat(self, prompt: str, system_prompt: str = None,
                    top_k: int = None, temperature: float = 0.98) -> Iterator[dict]: ...

    # --- Парсинг документов ---
    def parse_file(self, file_path: str) -> dict: ...
    def parse_file_stream(self, file_path: str) -> Iterator[dict]: ...
```

### Обработка SSE-стрима
```python
def stream_chat(self, prompt, system_prompt=None, top_k=None, temperature=0.98):
    payload = {"prompt": prompt, "temperature": temperature}
    if system_prompt: payload["system_prompt"] = system_prompt
    if top_k: payload["top_k"] = top_k

    resp = requests.post(f"{self.base_url}/rag/agent/stream",
                         json=payload, stream=True, timeout=120)
    for line in resp.iter_lines(decode_unicode=True):
        if line.startswith("data: "):
            yield json.loads(line[6:])
```

---

## 4. Блюпринты

### 4.1 `auth.py` — Аутентификация

| Route | Method | Описание |
|-------|--------|----------|
| `/login` | GET/POST | Форма входа. `POST`: проверка пароля, `login_user()` |
| `/register` | GET/POST | Регистрация (открыта, логин 3-32 `[A-Za-z0-9_.-]`, пароль ≥6 символов) |
| `/logout` | POST | `logout_user()`, редирект на `/login` |

- **Flask-Login**管理 сессиями. `@login_required` декоратор на защищённых маршрутах.
- CSRF-токены через **Flask-WTF** на всех формах.

### 4.2 `chat.py` — Чат и история

| Route | Method | Описание |
|-------|--------|----------|
| `/` | GET | Главная — чат-интерфейс |
| `/api/chat/stream` | POST | SSE-стриминг ответа RAG (прокси к `/rag/agent/stream`) |
| `/api/conversations` | GET | Список чатов пользователя (пагинация: `?page=1&per_page=50`) |
| `/api/conversations` | POST | Создать новый чат |
| `/api/conversations/<id>` | GET | Сообщения чата (пагинация: `?page=1&per_page=50`) |
| `/api/conversations/<id>` | DELETE | Удалить чат |
| `/api/conversations/<id>/title` | PUT | Переименовать чат |
| `/api/favorites` | GET | Список избранного (пагинация) |
| `/api/favorites` | POST | Добавить в избранное |
| `/api/favorites/<id>` | DELETE | Удалить из избранного |
| `/api/search/memos` | GET | Поиск мемо по `out/*.docx` (fuzzy) |

### 4.3 `memo.py` — Мастер мемо

| Route | Method | Описание |
|-------|--------|----------|
| `/api/memo/template` | GET | Поля шаблона `.dotx` |
| `/api/memo/variants` | GET | Варианты тела из `out/*.docx` по теме `?q=<topic>` |
| `/api/memo/suggest` | POST | RAG-подсказки для полей (прокси к `/rag/agent/stream`) |
| `/api/memo/docx` | POST | Сгенерировать и скачать `.docx` |

### 4.4 `admin.py` — Админ-панель

| Route | Method | Описание |
|-------|--------|----------|
| `/admin` | GET | Панель администратора |
| `/api/admin/info` | GET | Информация о системе (прокси к `/rag/info`, `/rag/engine/status`) |
| `/api/admin/config` | GET | Конфигурация (прокси к `/rag/config`) |
| `/api/admin/config` | PATCH | Обновить конфигурацию |
| `/api/admin/config/reset` | POST | Сброс конфигурации |
| `/api/admin/models` | GET | Список моделей |
| `/api/admin/provider` | GET/POST | Провайдер |
| `/api/admin/folders` | GET/POST | Папки сканирования |
| `/api/admin/sync` | POST | Запуск синхронизации |
| `/api/admin/users` | GET | Список пользователей |
| `/api/admin/users` | POST | Создать пользователя |
| `/api/admin/users/<id>` | DELETE | Удалить пользователя |
| `/api/admin/users/<id>/password` | PUT | Сменить пароль |
| `/api/admin/template` | POST | Загрузить новый `.dotx` шаблон |

---

## 5. Ключевые улучшения перед текущим Web UI

### 5.1 Безопасность
| Проблема сейчас | Решение |
|-----------------|---------|
| Пароли в plaintext | werkzeug.security (scrypt) |
| Открытая регистрация | Опция «только по приглашению» в конфиге |
| Нет CSRF | Flask-WTF csrf_token на всех формах |
| XSS через marked.js | DOMPurify перед рендером Markdown |
| Admin видит пароли | Убрать колонку паролей, показывать только действия |
| SECRET_KEY хардкод | Генерация при первом запуске, сохранение в `.env` |
| catch-all прокси | Only explicit API routes через `RAGClient` |
| test-parser без логина | `@login_required` на всех маршрутах |

### 5.2 Производительность
| Проблема сейчас | Решение |
|-----------------|---------|
| Весь корпус в RAM (10s кеш) | Пагинация + ленивое чтение, кеш только на уровне файлов |
| Вся история загружается | SQL-пагинация `LIMIT/OFFSET` |
| История перезагружается после каждого сохранения | Optimistic update на клиенте, AJAX only |
| Нет индексов | SQL-индексы на все lookup-поля |

### 5.3 UX
| Проблема сейчас | Решение |
|-----------------|---------|
| Sync overlay блокирует весь UI | Overlay с кнопкой «dismiss», чат доступен в read-only |
| Нет пагинации истории | Infinite scroll / кнопка «загрузить ещё» |
| Admin inline JS (530 строк) | Отдельный `admin.js` с cache-busting |
| Дублирующие system prompts | Единый `SYSTEM_PROMPTS` dict в `config.py` |
| localStorage-сессия мастера | Серверная сессия (Flask session) для состояния мастера |

---

## 6. Пошаговый план реализации

### Фаза 1: Инфраструктура и модель данных
1. Очистить `RAG System Web UI/` (удалить старый `app.py`, шаблоны, статику)
2. Создать `config.py` — конфигурация из env-переменных
3. Создать `extensions.py` — инициализация Flask-SQLAlchemy, Flask-Login, CSRF
4. Создать `models.py` — все 4 таблицы
5. Создать `requirements.txt` — Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Migrate, requests, python-docx, werkzeug
6. Инициализировать БД, начальная миграция
7. Создать `app.py` — точка входа, регистрация блюпринтов, seed admin-пользователя
8. Убедиться, что `python -m flask db upgrade` работает

### Фаза 2: API-клиент и аутентификация
9. Написать `api_client.py` — обёртку над RAG System API
10. Написать `auth.py` — блюпринт аутентификации (login, register, logout)
11. Написать `templates/auth/login.html` и `templates/auth/register.html`
12. Написать `templates/base.html` — базовый layout
13. Настроить `@require_login` декоратор через Flask-Login

### Фаза 3: Чат
14. Написать `chat.py` — блюпринт чата (главная, SSE-стриминг, CRUD историей)
15. Написать `templates/chat/index.html` — чат-интерфейс
16. Написать `static/js/app.js` — точка входа JS
17. Написать `static/js/chat.js` — SSE-стриминг, рендеринг сообщений, команды
18. Написать `static/js/history.js` — загрузка, пагинация, переключение чатов
19. Написать `static/js/utils.js` — fetch-обёртки, SSE-парсер, markdown
20. Написать `static/css/style.css` — стили чата

### Фаза 4: Мастер мемо
21. Написать `memo.py` — блюпринт мастера мемо
22. Написать `static/js/memo.js` — мастер мемо (state machine, формы, скачивание)
23. Интегрировать мастер в чат (команда `/create`)

### Фаза 5: Админ-панель
24. Написать `admin.py` — блюпринт админки
25. Написать `templates/admin/index.html` — админ-панель
26. Написать `static/js/admin.js` — логика админки
27. Написать `static/js/sync.js` — мониторинг синхронизации

### Фаза 6: Сборка и тестирование
28. Обновить `build.spec` под новую структуру
29. Протестировать все потоки (вход, чат, мемо, админка)
30. Проверить работу в frozen-режиме (PyInstaller)

---

## 7. Файлы для удаления (при очистке)

- `app.py` (текущий, 811 строк) → заменяется новым
- `memo_docx.py` → переносится без изменений (чистый утилитарный модуль)
- `templates/index.html` → заменяется
- `templates/admin.html` → заменяется
- `templates/login.html` → заменяется
- `templates/register.html` → заменяется
- `templates/test_parser.html` → удаляется (встроится в админку при необходимости)
- `static/js/main.js` → заменяется модулями
- `static/js/memo.js` → заменяется
- `static/css/style.css` → заменяется

## 8. Файлы для сохранения

- `memo_docx.py` — не трогаем, используется `memo.py` Blueprint
- `docx_templates/mmo.dotx` — шаблон мемо
- `build.spec` — обновляется под новую структуру
- `hook_runtime.py` — без изменений
- `.venv/` — пересоздаётся с новыми зависимостями

---

## 9. Зависимости (`requirements.txt`)

```
Flask>=3.0
Flask-SQLAlchemy>=3.1
Flask-Login>=0.6
Flask-WTF>=1.2
Flask-Migrate>=4.0
requests>=2.31
python-docx>=1.1
werkzeug>=3.0
```

---

## 10. Конфигурация (env-переменные)

| Переменная | Дефолт | Описание |
|-----------|--------|----------|
| `SECRET_KEY` | генерируется при первом запуске | Секрет Flask-сессий |
| `DATABASE_URL` | `sqlite:///data/app.db` | URL базы данных |
| `RAG_API_URL` | `http://127.0.0.1:11455/rag` | Базовый URL RAG System API |
| `PORT` | `80` | Порт Web UI |
| `OPEN_REGISTRATION` | `true` | Разрешена ли открытая регистрация |
| `MEMO_CORPUS_DIR` | `../out` | Путь к корпусу мемо (относительно app.py) |
| `MEMO_TEMPLATE_DIR` | `docx_templates` | Путь к шаблонам мемо |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | Дефолтный пароль admin при seed |
