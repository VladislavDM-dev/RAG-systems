# RAG System Web UI

Отдельный веб-интерфейс для сервиса **RAG System** (Flask API на порту `11455`, префикс `/rag`).
Страницы (чат, админка, тест парсера) взяты за основу из проекта `IndexDocuments` и адаптированы
под работу через HTTP API.

## Структура

```
RAG System Web UI/
├── app.py            # Flask-приложение: рендер страниц + прокси /rag/*
├── requirements.txt  # зависимости
├── templates/        # index.html (чат), admin.html, test_parser.html
├── static/           # css/bootstrap, bootstrap-icons, js/main.js, marked
└── tests/            # pytest-тесты
```

## Запуск

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Страницы:

- `http://127.0.0.1/` — чат (поиск с/без ИИ, SSE-стрим, история в localStorage).
- `http://127.0.0.1/admin` — админ-панель (инфо, настройки LLM, папки, синхронизация).
- `http://127.0.0.1/test-parser` — тест парсера (.doc/.docx/.pdf).

> Порт по умолчанию — `80` — требует прав администратора. Сменить порт можно
> переменной окружения `PORT` (например `set PORT=5000`).

## Настройка

| Переменная        | По умолчанию                  | Описание                          |
|-------------------|-------------------------------|-----------------------------------|
| `RAG_API_URL`     | `http://127.0.0.1:11455/rag`  | Базовый URL API сервиса RAG System|
| `PORT`            | `80`                          | Порт веб-интерфейса               |

Пример:

```bat
set RAG_API_URL=http://172.30.99.77:11455/rag
set PORT=5000
.venv\Scripts\python.exe app.py
```

## Как это работает

Веб-интерфейс сам не индексирует документы — все запросы проксируются на API
RAG System (через `requests`), поэтому CORS не требуется. Стриминговые
эндпоинты (`/rag/search/stream`, `/rag/parse/stream`) передаются как SSE.

Соответствие вызовов фронтенда и эндпоинтов API:

| JS (браузер)          | Прокси-путь            | Целевой эндпоинт RAG System       |
|-----------------------|------------------------|-----------------------------------|
| Чат                   | `/rag/search/stream`   | `POST /rag/search/stream` (SSE)   |
| Статус синхронизации  | `/rag/engine/status`   | `GET /rag/engine/status`          |
| Запуск синхронизации  | `/rag/index`           | `POST /rag/index`                 |
| Папки                 | `/rag/folders`         | `GET/POST /rag/folders`           |
| Сохранение настроек   | `/rag/config` (PATCH)  | `PATCH /rag/config`               |
| Модели бэкенда        | `/rag/models`          | `GET /rag/models`                 |
| Парсинг файла         | `/rag/parse`           | `POST /rag/parse`                 |

## Тесты

```bat
.venv\Scripts\python.exe -m pytest
```

Дымовые тесты проверяют рендер страниц при недоступном API, формат запроса
прокси и корректный статус 502 при выключенном сервисе RAG System.