# 12. Git и соглашения проекта

## 12.1 Структура репозитория

```
C:\Scripts\RAG systems\
├── .git/
├── .gitignore                      # корневой (см. ниже)
├── AGENTS.md                       # инструкции для ИИ-агентов
├── build_all.ps1                   # сборка обоих проектов (PyInstaller)
├── generate_memos.py               # перегенерация корпуса out/ (Word COM)
├── docx_templates/mmo.dotx         # шаблон служебки (бинарный, в git)
├── out/                            # корпус (gitignored)
├── RAG System/                     # ядро (свой venv)
└── RAG System Web UI/              # Web UI (свой venv)
```

## 12.2 Правила коммитов

- Сообщения **на английском**.
- Префиксы типов: `feat:`, `fix:`, реже `docs:`, `refactor:`, `chore:`, `test:`.
- Стиль — по `git log --oneline`, кратко и по делу:

```text
feat: add memo wizard variants to /create flow
fix: restore , "chat" via m56 (2025)
```

- **Не** делать `git push --force`, `git commit --amend`, пустые коммиты без явного запроса.
- Никогда не коммитить (см. `.gitignore`):
  - `RAG System Web UI/data/` (`app.db`, `secret_key`) — пользовательские данные;
  - `users.json` — если появится созданный при регистрации (вконце админ-панели) — локальные данные;
  - `RAG System/rag_engine/settings.json` — секреты/локальные пути/`api_key`;
  - `out/` — сгенерированный корпус;
  - `.cache/`, `.venv/`.

## 12.3 `.gitignore` (корневой)

- `out/` (уже есть), `extracted.txt`
- `RAG System Web UI/data/`, `users.json`
- `RAG System/rag_engine/settings.json`
- `build/`, `dist/`, `installer/Output/`
- `.venv/`, `.cache/`, среды, __pycache__
- `*.exe` не игнорируется — их не должно быть в дереве исходников

## 12.4 Конвенции кода

- Python: 4 пробела, Python 3.12; импорты по группам; без лишних абстракций.
- **Windows-специфично**: все обращения к Word COM — только через `_WORD_LOCK` (`docx_parser.py`), никаких параллельных Word. Не создавать несколько `Word.Application`.
- Бинарный шаблон `mmo.dotx` правится в Word: поля/плейсхолдеры — только `{{ key }}`; после сохранения diff больших бинарных изменений НЕ доверять — сверять со списком плейсхолдеров.
- Файлы в кодировке UTF-8, запуск — с `-X utf8` (иначе кириллица в `.docx` бьётся).
- В Web UI при любой правке `static/js/*.js` (или `static/css/*.css`) **бампать** `MEMO_JS_VERSION` — версия подставляется в шаблоны как `?v=...`.

## 12.5 Типичные workflows

```powershell
git status
git log --oneline -10
git add RAG\ System/app.py RAG\ System/rag_engine/rag_engine.py
git commit -m "fix: handle empty prompt in agent stream"
```

Два независимых проекта в одном репо — коммиты не смешивать по проектам без необходимости; при правке и ядра, и UI лучше два коммита.

## 12.6 Синхронизация с реальностью

- `AGENTS.md` — живой документ «как есть»: путь-запуск, требования к venv, `-X utf8`, тесты. При изменении поведения обязательно обновляйте его и этот раздел.
- Базу знаний по версии держать синхронно: `RAGEngine.VERSION` (ядро, `rag_engine/rag_engine.py`) и `MEMO_JS_VERSION` (Web UI, `config.py`) — версии-метки для диагностики версий в логе/браузере.