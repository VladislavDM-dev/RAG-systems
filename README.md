# RAG системы

Репозиторий содержит локальную RAG-систему поиска по корпоративным документам
(`.doc`, `.docx`, `.pdf`) и генератор служебных записок на её основе.

## Структура

```
RAG systems/
├── RAG System/            # Ядро: RAG-движок + собственный Flask API (порт 11455, префикс /rag)
├── RAG System Web UI/     # Веб-интерфейс (чат, админка, мастер служебных записок), порт 80
├── docx_templates/        # Шаблон служебной записки (mmo.dotx)
├── generate_memos.py      # Пакетная генерация записок по шаблону через Word COM
├── out/                   # Сгенерированные .docx (исключён из git)
├── IndexDocuments/        # Исходный проект, из которого выделен движок
└── README.md
```

## Компоненты

| Компонент | Назначение |
|-----------|------------|
| `RAG System` | Индексация (LlamaIndex + FAISS), парсеры `.doc`/`.docx`/`.pdf`, генерация через Ollama / LM Studio, REST API `/rag/*` |
| `RAG System Web UI` | Чат (SSE-стрим), админ-панель, мастер служебных записок (`/create`), история диалогов и избранного на сервере |
| `generate_memos.py` | Массовая генерация 200 записок в `out/` по шаблону, с заполнением полей и footer (исполнитель, телефон) через Word COM |

## Быстрый старт

```powershell
# 1. Ядро (RAG API) — порт 11455
cd "C:\Scripts\RAG systems\RAG System"
.\.venv\Scripts\python.exe app.py

# 2. Веб-интерфейс — порт 80
cd "C:\Scripts\RAG systems\RAG System Web UI"
.\.venv\Scripts\python.exe -X utf8 app.py
```

Локальные модели: **Ollama** или **LM Studio** (см. `RAG System/rag_engine/settings.json`).

## Ключевые сценарии

- **Чат с базой знаний** — вопросы по документам, ответы RAG с источниками.
- **Мастер служебной записки** — команда `/create <тема>` в чате: одно окно с
  вариантами текста (RAG), полями шапки (шаблон `mmo.dotx`), предпросмотром и
  скачиванием `.docx`. Связанные пары полей и состояние мастера
  восстанавливаются после обновления страницы.
- **Генерация записок** — `python generate_memos.py` (нужен `win32com`,
  см. README в `RAG System Web UI`).

## Документация

- [RAG System/README.md](RAG%20System/README.md) — ядро: настройки, API `/rag/*`, тесты.
- [RAG System Web UI/README.md](RAG%20System%20Web%20UI/README.md) — запуск, страницы, мастер записок.

## Требования

- Windows (парсеры используют Word COM для `.doc` и ABBYY FineReader для `.pdf`).
- Python 3.10+ с `-X utf8`.
- Запущенный Ollama или LM Studio с моделями (LLM + эмбеддинги).