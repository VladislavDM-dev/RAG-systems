# 05. API Web UI (`/api/*`)

Все endpoints требуют `login_required` (кроме страниц логина/регистрации). CSRF:
- `<form>`-методы (login/register/logout) требуют `csrf_token`;
- JSON-endpoints сохранения (POST/PUT/DELETE на `chat.py`, `memo.py`, `admin.py`) помечены `@csrf.exempt` — но это осознанный выбор проекта (см. AGENTS.md: формы защищены, API-часть отключена).

Базовые страницы: `GET /` (чат), `GET /admin` (админка), `GET /login`, `GET /register`.

## 5.1 Чат и стриминг

### `POST /api/chat/stream` (SSE)
Тело (JSON): `prompt` (обяз.), опц. `system_prompt`, `top_k`, `temperature`, `memos_paged`.

**Расписание (запрет):** источник — ядро (`GET /rag/schedule`, см. doc/04). Если для пользователя сейчас действует запрет (`schedule.py:get_restriction_message()` опрашивает ядро; админы не блокируются) → `403 {error: "<текст блокировки>", restricted: true}` до любых обращений к ядру.

Ветки:
- `memos_paged: true` → поиск записок (`_stream_memos`, temperature по умолч. 0.2);
- иначе если клиент не задал `system_prompt` и `detect_memos_topic(prompt)` вернул тему → поиск записок (temperature 0.0);
- иначе — обычный RAG-ответ SSE.

Проксирует события ядра 1:1: `sources / reasoning / token / done / error`. В `done` дополнительно: `answer, reasoning, sources` (дедуплицированы), `tokens_in, tokens_out, elapsed, mode`. Для ветки записок: быстрый путь ядра (по умолч.) → `sources` + `done` (без reasoning, ~50 мс); `use_llm=true` → `reasoning` + `done`. `done` содержит `documents` и `answer` (сводка из `_memos_answer`).

Пример запроса:
```json
{ "prompt": "Чем занимается отдел закупок?", "temperature": 0.3 }
```

### `GET /api/status`
Прокси `current_app.rag.index_status()` + поля расписания:
```json
{ "is_syncing": false, "status": "Готово к работе", "progress": 100,
  "sync_files": [], "initialized": true, "document_count": 53, "index_updated": "…",
  "restricted": false, "restriction_message": "" }
```
`restricted: true` → клиент не разблокирует инпуты и показывает `restriction_message` (баннер + статус).

### `POST /api/parse`
`{ "file_path": "…" }` → результат `rag.parse_file(...)`.

## 5.1a Уведомления, обратная связь, пароль

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/notifications` | незакрытые уведомления `{notifications: [{id, text, created_at}]}` |
| POST | `/api/notifications/<id>/dismiss` | отметить закрытым (клик/крестик); повторный вызов не ошибка |
| POST | `/api/feedback` | `{text}` (≤2000 симв.) → сообщение администратору об ошибке |
| POST | `/api/password` | `{current_password, new_password}` → смена собственного пароля (любой вошедший) |
| GET | `/api/schedule` | дата/время сервера + окна запрета: `{server_time, server_time_hm, weekday, restricted, restriction_message, restrictions: [{days, start_time, end_time, message, active, applies_now}]}` |

## 5.2 Диалоги

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/conversations?page=&per_page=` | список (по `updated_at desc`, пагинация по 50) |
| POST | `/api/conversations` | создать `{title}` → `{ok, conversation}` |
| GET | `/api/conversations/<id>` | диалог + все `messages` (права владельца) |
| PUT | `/api/conversations/<id>` | переименовать `{title}` |
| DELETE | `/api/conversations/<id>` | удалить (каскадно сообщения) |

При доступе к чужому диалогу — `404` (first_or_404 с фильтром user_id).

## 5.3 Сообщения

### `POST /api/messages`
```json
{
  "conversation_id": 1,
  "role": "user|bot",
  "content": "…",
  "sources": [...],      // опц., сохраняется JSON в sources_json
  "memo_data": [...],    // опц., сохраняется в memo_data_json
  "skip_touch": false    // true — не обновлять updated_at диалога
}
```
→ `{ok, message}`.

## 5.4 Избранное

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/favorites?page=&per_page=` | список | 
| POST | `/api/favorites` | `{title, content, sources, memo_data}` |
| DELETE | `/api/favorites/<id>` | удалить избранное |

## 5.5 Мастер служебной записки

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/memo/template` | поля шаблона `{fields: [{key,label,hint}], path, updated}` |
| GET | `/api/memo/state` | состояние мастера пользователя `{state: {...}}` |
| POST | `/api/memo/state` | сохранить `{state}` (JSON) |
| DELETE | `/api/memo/state` | очистить состояние |
| POST | `/api/memo/docx` | собрать `.docx`: тело = сами поля (`{recipient_position, body, ...}`) → `<file> sluzhebnaya_zapiska.docx` |

`POST /api/memo/docx` возвращает бинарный `.docx` (mime `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). Ошибки: `{error}` + 500 (в т.ч. если шаблон не найден).

## 5.6 Админка (только роль `admin`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/admin/info` | статус (версия, документы, index_updated, backend, provider, синхронизация) |
| GET | `/api/admin/config` | конфиг RAG |
| PATCH | `/api/admin/config` | обновить (те же ключи, что `PATCH /rag/config`) |
| POST | `/api/admin/config/reset` | сброс + пересинхронизация |
| GET | `/api/admin/models` | модели бэкенда |
| GET/POST | `/api/admin/provider` | провайдер |
| GET/POST | `/api/admin/folders` | папки синхронизации |
| POST | `/api/admin/sync` | `{reset}` → запуск синхронизации |
| GET/POST | `/api/admin/users` | список / создать пользователя |
| DELETE | `/api/admin/users/<uid>` | удалить (без админов!) |
| PUT | `/api/admin/users/<uid>/password` | сменить пароль |
| POST | `/api/admin/memo/template/reload` | перечитать шаблон mmo.dotx |
| POST | `/api/admin/memo/template` | загрузить новый `.dotx` (multipart `file`) |
| GET/POST | `/api/admin/schedule` | **прокси ядра** `/rag/schedule`: список / создать `{days:[0..6], start_time, end_time, message, active?}` |
| PUT/DELETE | `/api/admin/schedule/<rid>` | **прокси ядра**: обновить (частичный, напр. `{active}`) / удалить |
| GET/POST | `/api/admin/notifications` | список / создать `{text}` |
| DELETE | `/api/admin/notifications/<nid>` | удалить (вместе с отметками о закрытии) |
| GET | `/api/admin/messages` | сообщения пользователей (непрочитанные сверху) |
| POST | `/api/admin/messages/<mid>/read` | `{is_read}` — отметить прочитанным/нет |
| DELETE | `/api/admin/messages/<mid>` | удалить сообщение |

Не-админ → `403 {error}`.

Валидация расписания живёт в ядре (`rag_engine/schedule.py`): `days` — непустой список 0..6 (0=Пн); `start_time`/`end_time` — `HH:MM`; `message` — непустой текст блокировки. `start == end` — запрет на весь день; диапазон через полночь поддерживается. Ошибки валидации ядра Web UI возвращает как 400.

## 5.7 Итоговая таблица форм-страниц

| Метод | Путь | Примечание |
|---|---|---|
| GET/POST | `/login` | форма + вход |
| GET/POST | `/register` | регистрация (если `OPEN_REGISTRATION`) |
| POST | `/logout` | выход |
| GET | `/` | чат (SPA) |
| GET | `/admin` | админ-панель |