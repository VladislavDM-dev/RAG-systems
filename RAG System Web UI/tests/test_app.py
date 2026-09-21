"""Смоук-тесты нового Web UI: аутентификация, чат/история, избранное, мемо, админка."""


# --- Аутентификация ---

def test_login_page_ok(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Войти" in resp.get_data(as_text=True)


def test_anonymous_redirected_to_login(client):
    for path in ("/", "/api/status", "/admin"):
        resp = client.get(path)
        assert resp.status_code == 302


def test_login_wrong_password(client):
    token = client.get("/login").get_data(as_text=True)
    import re
    tok = re.search(r'name="csrf_token" value="([^"]+)"', token).group(1)
    resp = client.post("/login", data={
        "username": "admin", "password": "nope", "csrf_token": tok,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Неверный логин или пароль" in resp.get_data(as_text=True)


def test_login_bad_csrf(client):
    resp = client.post("/login", data={
        "username": "admin", "password": "admin123", "csrf_token": "bad",
    })
    assert resp.status_code == 400


def test_logout(logged_client):
    import re
    page = logged_client.get("/").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    resp = logged_client.post("/logout", data={"csrf_token": tok}, follow_redirects=True)
    assert resp.status_code == 200
    assert logged_client.get("/api/status").status_code == 302


# --- Чат и история ---

def test_chat_page(logged_client):
    resp = logged_client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "question-input" in html


def test_conversation_crud(logged_client):
    resp = logged_client.get("/api/conversations")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0

    resp = logged_client.post("/api/conversations", json={"title": "Тест чат"})
    assert resp.status_code == 200
    conv = resp.get_json()["conversation"]
    assert conv["title"] == "Тест чат"

    resp = logged_client.get("/api/conversations")
    assert resp.get_json()["total"] == 1


def test_messages_roundtrip(logged_client):
    conv = logged_client.post("/api/conversations", json={"title": "T"}).get_json()["conversation"]
    cid = conv["id"]
    logged_client.post("/api/messages", json={
        "conversation_id": cid, "role": "user", "content": "вопрос",
    })
    logged_client.post("/api/messages", json={
        "conversation_id": cid, "role": "bot", "content": "ответ",
        "sources": [{"file_name": "a.docx", "file_path": "/x/a.docx", "score": 0.9}],
    })
    resp = logged_client.get(f"/api/conversations/{cid}")
    messages = resp.get_json()["messages"]
    assert len(messages) == 2
    assert messages[1]["role"] == "bot"
    assert messages[1]["sources"][0]["file_name"] == "a.docx"

    logged_client.delete(f"/api/conversations/{cid}")
    assert logged_client.get(f"/api/conversations/{cid}").status_code == 404


def test_favorites_roundtrip(logged_client):
    resp = logged_client.post("/api/favorites", json={
        "title": "Фаворит", "content": "Текст фаворита",
    })
    assert resp.status_code == 200
    fid = resp.get_json()["favorite"]["id"]

    data = logged_client.get("/api/favorites").get_json()
    assert data["total"] == 1
    assert data["favorites"][0]["title"] == "Фаворит"

    assert logged_client.delete(f"/api/favorites/{fid}").status_code == 200
    assert logged_client.get("/api/favorites").get_json()["total"] == 0


# --- Мемо ---

def test_memo_template(logged_client):
    resp = logged_client.get("/api/memo/template")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "fields" in data


def test_memo_state_save_load_clear(logged_client):
    # Пустое состояние по умолчанию.
    resp = logged_client.get("/api/memo/state")
    assert resp.status_code == 200
    assert resp.get_json()["state"] == {}

    # Сохранение состояния мастера.
    resp = logged_client.post("/api/memo/state", json={
        "state": {"step": "fields", "topic": "Канцтовары", "fields": {"date": "01.01.2026"}},
    })
    assert resp.status_code == 200

    # Загрузка.
    resp = logged_client.get("/api/memo/state")
    assert resp.status_code == 200
    state = resp.get_json()["state"]
    assert state["topic"] == "Канцтовары"
    assert state["fields"]["date"] == "01.01.2026"

    # Очистка.
    resp = logged_client.delete("/api/memo/state")
    assert resp.status_code == 200
    resp = logged_client.get("/api/memo/state")
    assert resp.get_json()["state"] == {}


def test_memo_state_requires_object(logged_client):
    resp = logged_client.post("/api/memo/state", json={"state": "not-a-dict"})
    assert resp.status_code == 400


def test_memos_routes_removed(logged_client):
    # Локальный корпус убран: всё через RAG.
    assert logged_client.get("/api/memos").status_code == 404
    assert logged_client.get("/api/search/memos").status_code == 404


# --- Поиск записок через ядро (/memos) ---

class ScriptedMemosRAG:
    """Имитирует ответ ядра /memos: список документов с полным текстом."""

    def __init__(self, documents=None, error=None):
        self.documents = documents or []
        self.error = error
        self.stream_chat_called = False
        self.memos_called = False

    def memos(self, prompt, temperature=0.2, page_size=30, max_pages=15):
        self.memos_called = True
        if self.error:
            return {"error": self.error}
        return {"ok": True, "total": len(self.documents), "documents": self.documents}

    def stream_chat(self, prompt, **kwargs):
        self.stream_chat_called = True
        yield {"type": "error", "data": "не должен вызываться"}


def _parse_sse(resp):
    events = []
    for line in resp.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            import json
            events.append(json.loads(line[6:]))
    return events


def test_memos_renders_documents(logged_client):
    import app as app_module
    stub = ScriptedMemosRAG(documents=[
        {
            "file_name": "#10-2026.02.03-О закупке канцелярских принадлежностей.docx",
            "file_path": "C:\\out\\#10-2026.02.03.docx",
            "text": "Служебная записка №10 от 03.02.2026\nТекст первой записки.",
        },
        {
            "file_name": "#27-2026.04.01-Канцтовары.docx",
            "file_path": "C:\\out\\#27-2026.04.01.docx",
            "text": "Служебная записка №27 от 01.04.2026\nТекст второй записки.",
        },
    ])
    app_module.app.rag = stub

    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "/memos канцтовары",
        "memos_paged": True,
    })
    assert resp.status_code == 200
    done = next(e for e in _parse_sse(resp) if e["type"] == "done")
    assert "#10-2026.02.03-О закупке канцелярских принадлежностей.docx" in done["answer"]
    assert "C:\\out\\#10-2026.02.03.docx" in done["answer"]
    assert "Текст первой записки." in done["answer"]
    assert "#27-2026.04.01-Канцтовары.docx" in done["answer"]
    assert "Текст второй записки." in done["answer"]
    assert "Итого записок по теме: 2" in done["answer"]
    assert not done.get("sources")


def test_memos_empty(logged_client):
    import app as app_module
    app_module.app.rag = ScriptedMemosRAG(documents=[])
    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "/memos ничего", "memos_paged": True,
    })
    done = next(e for e in _parse_sse(resp) if e["type"] == "done")
    assert "не найдены" in done["answer"]


def test_memos_error(logged_client):
    import app as app_module
    app_module.app.rag = ScriptedMemosRAG(error="Индекс не готов")
    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "/memos канцтовары", "memos_paged": True,
    })
    events = _parse_sse(resp)
    assert any(e["type"] == "error" for e in events)
    assert not any(e["type"] == "done" for e in events)


def test_memos_auto_detected_without_command(logged_client):
    """Обычный запрос со словами-маркерами уходит в поиск служебок."""
    import app as app_module
    app_module.app.rag = ScriptedMemosRAG(documents=[{
        "file_name": "#10-2026.02.03-О закупке канцелярских принадлежностей.docx",
        "file_path": "C:\\out\\#10-2026.02.03.docx",
        "text": "Текст первой записки.",
    }])
    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "покажи служебные записки по канцтоварам",
    })
    done = next(e for e in _parse_sse(resp) if e["type"] == "done")
    assert "#10-2026.02.03-О закупке канцелярских принадлежностей.docx" in done["answer"]
    assert "Итого записок по теме: 1" in done["answer"]


def test_memos_not_auto_for_plain_question(logged_client):
    """Вопрос без маркеров не уходит в поиск служебок."""
    import app as app_module
    stub = ScriptedMemosRAG(documents=[{
        "file_name": "#10.docx", "file_path": "C:\\out\\#10.docx", "text": "x",
    }])
    app_module.app.rag = stub
    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "сколько стоят канцтовары?",
    })
    assert stub.stream_chat_called is True
    events = _parse_sse(resp)
    assert any(e["type"] == "error" for e in events)
    assert not any(e["type"] == "done" for e in events)


def test_memos_not_auto_with_explicit_system_prompt(logged_client):
    """Мастер записки шлёт явный system_prompt; промпт с маркером «записка»
    не должен перехватываться поиском служебок и обязан идти в стрим."""
    import app as app_module
    stub = ScriptedMemosRAG(documents=[{
        "file_name": "#10.docx", "file_path": "C:\\out\\#10.docx", "text": "x",
    }])
    app_module.app.rag = stub
    resp = logged_client.post("/api/chat/stream", json={
        "prompt": "Служебная записка по теме: канцтовары. Подготовь несколько вариантов текста.",
        "system_prompt": "Ты — помощник по генерации служебных записок.",
    })
    assert stub.stream_chat_called is True
    assert stub.memos_called is False
    events = _parse_sse(resp)
    assert any(e["type"] == "error" for e in events)
    assert not any(e["type"] == "done" for e in events)


# --- Админка ---

def test_admin_requires_admin(logged_client):
    # admin в seeded-БД — администратор.
    resp = logged_client.get("/admin")
    assert resp.status_code == 200


def test_admin_users_create_delete(logged_client):
    resp = logged_client.post("/api/admin/users", json={
        "username": "user1", "password": "secret1",
    })
    assert resp.status_code == 200
    users = resp.get_json()["users"]
    uid = next(u["id"] for u in users if u["username"] == "user1")

    resp = logged_client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 200
    names = [u["username"] for u in resp.get_json()["users"]]
    assert "user1" not in names


def test_admin_cannot_delete_self(logged_client):
    resp = logged_client.get("/api/admin/users")
    admin_id = next(u["id"] for u in resp.get_json()["users"] if u["role"] == "admin")
    resp = logged_client.delete(f"/api/admin/users/{admin_id}")
    assert resp.status_code == 400


def test_admin_info(logged_client):
    resp = logged_client.get("/api/admin/info")
    assert resp.status_code == 200
    assert resp.get_json()["version"] == "test"


def test_status_endpoint(logged_client):
    resp = logged_client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json()["initialized"] is True


# --- Авто-детекция поиска служебок (detect_memos_topic) ---

from chat import detect_memos_topic


def test_detect_memos_topic_markers():
    assert detect_memos_topic("покажи записки по канцтоварам") == "канцтоварам"
    assert detect_memos_topic("найди служебные записки о закупке бумаги") == "закупке бумаги"
    assert detect_memos_topic("найди все записки про отпуска") == "отпуска"
    assert detect_memos_topic("мемо по командировкам") == "командировкам"
    assert detect_memos_topic("найди служебки про повышение зарплаты") == "повышение зарплаты"


def test_detect_memos_topic_ignores_questions():
    assert detect_memos_topic("что такое служебная записка") is None
    assert detect_memos_topic("как написать записку на отпуск") is None
    assert detect_memos_topic("как оформить записку") is None


def test_detect_memos_topic_plain_queries():
    assert detect_memos_topic("сколько стоят канцтовары?") is None
    assert detect_memos_topic("покажи мемо") is None
    assert detect_memos_topic(None) is None
    assert detect_memos_topic("") is None