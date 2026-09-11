import io
import json

import requests

import app as app_module


def test_index_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Войти" in resp.get_data(as_text=True)


def test_login_wrong_password(client, monkeypatch):
    monkeypatch.setattr(app_module, "authenticate", lambda u, p: False)
    resp = client.post("/login", data={"username": "admin", "password": "bad"})
    assert resp.status_code == 200
    assert "Неверный логин или пароль" in resp.get_data(as_text=True)


def test_login_success_redirects(client, monkeypatch):
    monkeypatch.setattr(app_module, "authenticate", lambda u, p: True)
    resp = client.post("/login", data={"username": "admin", "password": "x", "next": "/"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess["user"] = "admin"
    resp = client.post("/logout")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert "user" not in sess


def test_index_renders_for_auth_user(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "Выйти" in text
    assert "admin" in text


def test_index_has_no_mode_selector(auth_client):
    resp = auth_client.get("/")
    text = resp.get_data(as_text=True)
    assert "mode-selector-trigger" not in text
    assert "continue-btn" not in text
    assert "Поиск без ИИ" not in text
    assert "Поиск с ИИ" not in text


def test_index_has_agent_chat_ui(auth_client):
    resp = auth_client.get("/")
    text = resp.get_data(as_text=True)
    assert "question-input" in text
    assert "send-btn" in text
    assert "conversationsTab" in text
    assert "answersTab" in text


def test_proxy_requires_login(client, monkeypatch):
    resp = client.post("/rag/agent/stream", json={"prompt": "x"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_history_requires_login(client):
    resp = client.get("/api/history")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_history_roundtrip(auth_client):
    conv = {"id": "c1", "question": "Вопрос", "messages": [{"role": "user", "text": "Вопрос"}], "date": 1}
    r1 = auth_client.put("/api/conversations", json=conv)
    assert r1.status_code == 200
    assert r1.get_json()["ok"] is True

    ans = {"id": "a1", "question": "Вопрос", "answer": "Ответ", "date": 1}
    r2 = auth_client.put("/api/answers", json=ans)
    assert r2.status_code == 200

    hist = auth_client.get("/api/history").get_json()
    assert len(hist["conversations"]) == 1
    assert hist["conversations"][0]["id"] == "c1"
    assert len(hist["answers"]) == 1
    assert hist["answers"][0]["id"] == "a1"


def test_history_is_per_user(client, monkeypatch):
    monkeypatch.setattr(app_module, "authenticate", lambda u, p: True)
    with client.session_transaction() as sess:
        sess["user"] = "alice"
    client.put("/api/conversations", json={"id": "ca", "question": "q", "date": 1})

    with client.session_transaction() as sess:
        sess["user"] = "bob"
    hist = client.get("/api/history").get_json()
    assert hist["conversations"] == []


def test_upsert_replaces_existing(auth_client):
    auth_client.put("/api/conversations", json={"id": "c1", "question": "q1", "date": 1})
    auth_client.put("/api/conversations", json={"id": "c1", "question": "q2", "date": 2})
    convs = auth_client.get("/api/history").get_json()["conversations"]
    assert len(convs) == 1
    assert convs[0]["question"] == "q2"


def test_delete_conversation(auth_client):
    auth_client.put("/api/conversations", json={"id": "c1", "question": "q", "date": 1})
    auth_client.delete("/api/conversations/c1")
    assert auth_client.get("/api/history").get_json()["conversations"] == []


def test_delete_answer(auth_client):
    auth_client.put("/api/answers", json={"id": "a1", "question": "q", "date": 1})
    auth_client.delete("/api/answers/a1")
    assert auth_client.get("/api/history").get_json()["answers"] == []


def test_clear_history(auth_client):
    auth_client.put("/api/conversations", json={"id": "c1", "question": "q", "date": 1})
    auth_client.put("/api/answers", json={"id": "a1", "question": "q", "date": 1})
    auth_client.post("/api/history/clear")
    hist = auth_client.get("/api/history").get_json()
    assert hist["conversations"] == []
    assert hist["answers"] == []


def test_admin_renders_with_fallbacks(auth_client, monkeypatch):
    monkeypatch.setattr(app_module, "get_json", lambda *a, **k: {})
    resp = auth_client.get("/admin")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "Админ-панель" in text
    assert app_module.DEFAULT_CONFIG["llm"] in text
    assert app_module.DEFAULT_CONFIG["llm_embed"] in text
    assert 'id="provider-select"' in text
    assert 'value="ollama" selected' in text
    assert 'id="api-key-input"' in text


def test_admin_renders_lmstudio_selected(auth_client, monkeypatch):
    responses = {
        "engine/status": {"is_initialized": True, "index_updated": "2026-01-01T00:00:00"},
        "config": {"provider": "lmstudio", "url": "http://127.0.0.1:1234/v1"},
        "models": {},
    }
    monkeypatch.setattr(app_module, "get_json",
                        lambda endpoint, **k: responses.get(endpoint, {}))
    resp = auth_client.get("/admin")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'value="lmstudio" selected' in text
    assert 'value="ollama"' in text


def test_admin_shows_users_table(auth_client):
    resp = auth_client.get("/admin")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "Пользователи" in text
    assert "users-table-body" in text
    assert "admin" in text


def test_test_parser_renders(client):
    resp = client.get("/test-parser")
    assert resp.status_code == 200
    assert "Тестирование Word Парсера" in resp.get_data(as_text=True)


def test_get_json_parses_response(client, monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)

        class Resp:
            status_code = 200

            def json(self):
                return {"x": 1}

        return Resp()

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    assert app_module.get_json("info") == {"x": 1}
    assert calls == [app_module.RAG_API_URL + "/info"]


def test_get_json_handles_api_down(client, monkeypatch):
    def fake_get(url, timeout):
        raise requests.RequestException("down")

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    assert app_module.get_json("info") == {}


def test_proxy_forwards_and_relays(auth_client, monkeypatch):
    class FakeResp:
        status_code = 200
        content = b"payload"
        headers = {"Content-Type": "text/event-stream"}

        def iter_content(self, chunk_size=None):
            yield b"payload"

        def close(self):
            pass

    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(
            method=method,
            url=url,
            params=kwargs.get("params"),
            data=kwargs.get("data"),
        )
        return FakeResp()

    monkeypatch.setattr(app_module.requests, "request", fake_request)

    resp = auth_client.post("/rag/agent/stream", json={"prompt": "q"}, query_string={"a": "1"})

    assert resp.status_code == 200
    assert resp.get_data() == b"payload"
    assert captured["method"] == "POST"
    assert captured["url"] == app_module.RAG_API_URL + "/agent/stream"
    assert captured["params"] == {"a": "1"}
    sent = json.loads(captured["data"])
    assert sent == {"prompt": "q", "system_prompt": app_module.AGENT_SYSTEM_PROMPT}


def test_proxy_system_prompt_not_overridden(auth_client, monkeypatch):
    class FakeResp:
        status_code = 200
        content = b"payload"
        headers = {"Content-Type": "text/event-stream"}

        def iter_content(self, chunk_size=None):
            yield b"payload"

        def close(self):
            pass

    captured = {}

    def fake_request(method, url, **kwargs):
        captured["data"] = kwargs.get("data")
        return FakeResp()

    monkeypatch.setattr(app_module.requests, "request", fake_request)

    auth_client.post("/rag/agent/stream", json={"prompt": "q", "system_prompt": "Будь краток."})
    assert json.loads(captured["data"]) == {"prompt": "q", "system_prompt": "Будь краток."}


def test_proxy_stream_uses_stream(auth_client, monkeypatch):
    class FakeStream:
        status_code = 200
        headers = {"Content-Type": "text/event-stream"}

        def iter_content(self, chunk_size=None):
            yield b"data: test\n\n"

        def close(self):
            pass

    captured = {}

    def fake_request(method, url, **kwargs):
        captured["stream"] = kwargs.get("stream")
        return FakeStream()

    monkeypatch.setattr(app_module.requests, "request", fake_request)

    resp = auth_client.post("/rag/agent/stream", json={"prompt": "q"})

    assert resp.status_code == 200
    assert captured["stream"] is True
    assert resp.mimetype == "text/event-stream"
    assert b"data: test" in resp.get_data()


def test_proxy_502_when_api_down(auth_client, monkeypatch):
    def fake_request(method, url, **kwargs):
        raise requests.RequestException("down")

    monkeypatch.setattr(app_module.requests, "request", fake_request)

    resp = auth_client.get("/rag/health")
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "RAG System API недоступен"


def test_ensure_users_file_creates_admin(tmp_path):
    users_file = tmp_path / "users.json"
    app_module.USERS_FILE = str(users_file)
    app_module._ensure_users_file()
    data = json.loads(users_file.read_text(encoding="utf-8"))
    assert "admin" in data["users"]
    assert data["users"]["admin"] == app_module.DEFAULT_ADMIN_PASSWORD
    # пароль admin123 подходит
    assert app_module.authenticate("admin", app_module.DEFAULT_ADMIN_PASSWORD)
    assert not app_module.authenticate("admin", "wrong")


def test_register_new_user_flow(auth_client, tmp_path, monkeypatch):
    # Регистрация нового пользователя через форму.
    resp = auth_client.post("/register", data={
        "username": "vasya",
        "password": "123456",
        "password2": "123456",
    })
    assert resp.status_code == 302
    assert app_module.authenticate("vasya", "123456")


def test_register_password_mismatch(client, monkeypatch):
    resp = client.post("/register", data={
        "username": "vasya",
        "password": "1111",
        "password2": "2222",
    })
    assert resp.status_code == 200
    assert "Пароли не совпадают" in resp.get_data(as_text=True)


def test_register_duplicate_user(client, monkeypatch):
    # admin уже существует в users.json (temp-файл).
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    app_module.USERS_FILE = path
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": {"admin": "x"}}, f)
        app_module._write_users({"users": {"admin": "x"}})
        resp = client.post("/register", data={
            "username": "admin",
            "password": "1111",
            "password2": "1111",
        })
        text = resp.get_data(as_text=True)
        assert "Такой логин уже существует" in text
    finally:
        os.remove(path)


def test_admin_requires_admin_role(client):
    # Обычный пользователь не имеет права на /admin.
    with client.session_transaction() as sess:
        sess["user"] = "vasya"
    resp = client.get("/admin")
    assert resp.status_code == 403


def test_admin_api_users_list_requires_admin(client):
    with client.session_transaction() as sess:
        sess["user"] = "vasya"
    resp = client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_api_add_delete_user(auth_client, tmp_path, monkeypatch):
    # Админ создаёт и удаляет пользователя.
    resp = auth_client.post("/api/admin/users", json={"username": "petya", "password": "pass123"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert any(u["username"] == "petya" and u["password"] == "pass123" for u in data["users"])

    resp = auth_client.delete("/api/admin/users/petya")
    data = resp.get_json()
    assert data["ok"] is True
    assert all(u["username"] != "petya" for u in data["users"])


def test_admin_cannot_delete_admin(auth_client, monkeypatch):
    resp = auth_client.delete("/api/admin/users/admin")
    assert resp.status_code == 400


def test_admin_set_password(auth_client, tmp_path, monkeypatch):
    auth_client.post("/api/admin/users", json={"username": "petya", "password": "pass123"})
    resp = auth_client.put("/api/admin/users/petya/password", json={"password": "newpass"})
    assert resp.status_code == 200
    assert app_module.authenticate("petya", "newpass")
    assert not app_module.authenticate("petya", "pass123")


def test_dedupe_sources_keeps_best_score():
    sources = [
        {"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.5},
        {"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.9},
        {"file_name": "b.doc", "file_path": "C:\\b.doc", "score": 0.7},
        {"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.8},
    ]
    result = app_module._dedupe_sources(sources)
    assert len(result) == 2
    assert {s["file_path"] for s in result} == {"C:\\a.doc", "C:\\b.doc"}
    a = next(s for s in result if s["file_path"] == "C:\\a.doc")
    assert a["score"] == 0.9


def test_generate_stream_dedupes_sources(monkeypatch):
    class FakeStream:
        status_code = 200

        def iter_content(self, chunk_size=None):
            srcs = [
                {"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.5},
                {"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.9},
                {"file_name": "b.doc", "file_path": "C:\\b.doc", "score": 0.7},
            ]
            lines = [
                ('data: {"type": "sources", "data": %s}\n\n' % json.dumps(srcs)).encode("utf-8"),
                b"data: {\"type\": \"token\", \"data\": \"x\"}\n\n",
                ('data: {"type": "done", "answer": "x", "sources": %s}\n\n' % json.dumps(srcs)).encode("utf-8"),
            ]
            yield from lines

        def close(self):
            pass

    out = b"".join(app_module.generate_stream(FakeStream()))
    text = out.decode("utf-8")
    events = [json.loads(l.split("data: ", 1)[1])
              for l in text.strip().split("\n\n") if l.startswith("data: ")]
    src_event = next(e for e in events if e["type"] == "sources")
    done_event = next(e for e in events if e["type"] == "done")
    assert len(src_event["data"]) == 2
    assert len(done_event["sources"]) == 2
    assert [s["file_path"] for s in done_event["sources"]] == ["C:\\a.doc", "C:\\b.doc"]


def test_memo_template_returns_fields(client):
    resp = client.get("/api/memo/template")
    assert resp.status_code == 200
    data = resp.get_json()
    fields = data["fields"]
    assert len(fields) >= 5
    keys = [f["key"] for f in fields]
    assert "body" in keys
    assert "recipient_position" in keys
    assert "sender_short_name" in keys
    assert all("label" in f and "key" in f for f in fields)
    assert any(f["hint"] for f in fields if f["key"] == "body")


def test_memo_template_reload_admin_required(client):
    resp = client.post("/api/admin/memo/template/reload")
    assert resp.status_code == 403


def test_memo_template_reload(auth_client):
    resp = auth_client.post("/api/admin/memo/template/reload")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "recipient_position" in data["fields"]


def test_memo_template_upload(auth_client, tmp_path):
    import memo_docx
    src = memo_docx.TEMPLATE_PATH
    with open(src, "rb") as f:
        content = f.read()
    resp = auth_client.post(
        "/api/admin/memo/template",
        data={"file": (io.BytesIO(content), "mmo.dotx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "body" in data["fields"]


def test_memo_template_upload_rejects_non_dotx(auth_client):
    resp = auth_client.post(
        "/api/admin/memo/template",
        data={"file": (io.BytesIO(b"bad"), "memo.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_memo_docx_returns_file(auth_client):
    resp = auth_client.post("/api/memo/docx", json={
        "recipient_position": "Начальнику отдела",
        "recipient_name": "Иванову И. И.",
        "memo_number": "1",
        "date": "08.09.2026",
        "body": "Тело записки.\nВторой абзац.",
        "sender_position": "Юрисконсульту",
        "sender_short_name": "Петров П. П.",
    })
    assert resp.status_code == 200
    assert resp.data[:2] == b"PK"
    assert "wordprocessingml.document" in resp.headers.get("Content-Type", "")


def test_memo_docx_requires_login(client):
    resp = client.post("/api/memo/docx", json={})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]