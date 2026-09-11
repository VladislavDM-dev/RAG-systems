import json


def test_health(client):
    r = client.get("/rag/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_info(client):
    r = client.get("/rag/info")
    assert r.status_code == 200
    data = r.get_json()
    assert data["service"] == "RAG System"
    assert data["provider"] in ("ollama", "lmstudio")
    assert isinstance(data["document_count"], int)


def test_engine_status(client):
    r = client.get("/rag/engine/status")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("is_initialized", "is_syncing", "status", "progress",
                "status_backend", "document_count"):
        assert key in data


def test_config_get(client):
    r = client.get("/rag/config")
    assert r.status_code == 200
    data = r.get_json()
    assert data["provider"] == "ollama"
    assert data["chunk_size"] == 256
    assert "sync_folders" in data


def test_config_patch_and_rollback(client):
    original = client.get("/rag/config").get_json()["similarity_top_k"]
    target = original + 3  # гарантированно отличается от текущего

    r = client.patch("/rag/config", json={"similarity_top_k": target})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["changed"] == ["similarity_top_k"]
    assert body["config"]["similarity_top_k"] == target

    # Возвращаем на место
    r = client.patch("/rag/config", json={"similarity_top_k": original})
    assert r.status_code == 200
    assert r.get_json()["config"]["similarity_top_k"] == original


def test_config_patch_invalid_field(client):
    r = client.patch("/rag/config", json={"wat": 1})
    assert r.status_code == 400


def test_config_patch_bad_provider(client):
    r = client.patch("/rag/config", json={"provider": "vllm"})
    assert r.status_code == 400


def test_folders_roundtrip(client):
    original = client.get("/rag/folders").get_json()["folders"]

    folders = ["C:\\Docs", "D:\\Архив\\2026"]
    r = client.post("/rag/folders", json={"folders": folders})
    assert r.status_code == 200
    assert r.get_json()["folders"] == folders

    assert client.get("/rag/folders").get_json()["folders"] == folders

    # Откат
    client.post("/rag/folders", json={"folders": original})


def test_folders_bad_payload(client):
    r = client.post("/rag/folders", json={"folders": "not-a-list"})
    assert r.status_code == 400


def test_provider_get(client):
    r = client.get("/rag/provider")
    assert r.status_code == 200
    data = r.get_json()
    assert data["provider"] == "ollama"
    assert "models" in data


def test_provider_set_valid(client, monkeypatch):
    import app as app_module

    engine = app_module.engine
    # Не ходим в сеть при смене провайдера
    monkeypatch.setattr(engine, "_RAGEngine__init_backend", lambda: True)
    monkeypatch.setattr(engine, "_RAGEngine__check_backend", lambda: None)

    r = client.post("/rag/provider", json={"provider": "lmstudio"})
    assert r.status_code == 200
    assert r.get_json()["provider"] == "lmstudio"

    # Обратно на ollama, чтобы не менять конфиг пакета
    client.post("/rag/provider", json={"provider": "ollama"})


def test_provider_switch_adjusts_default_url(client, monkeypatch):
    import app as app_module

    engine = app_module.engine
    original = engine.cfg.to_dict()
    monkeypatch.setattr(engine, "_RAGEngine__init_backend", lambda: True)
    monkeypatch.setattr(engine, "_RAGEngine__check_backend", lambda: None)

    # Ставим url по умолчанию ollama и переключаемся на lmstudio —
    # url должен автоматически смениться на адрес LM Studio.
    engine.cfg.update(provider="ollama", url="http://127.0.0.1:11434")
    r = client.post("/rag/provider", json={"provider": "lmstudio"})
    assert r.status_code == 200
    assert engine.cfg.url == "http://127.0.0.1:1234/v1"

    # Пользовательский (не-дефолтный) url не должен перезаписываться.
    engine.cfg.update(provider="ollama", url="http://remote-host:12345", api_key="k")
    r = client.post("/rag/provider", json={"provider": "lmstudio"})
    assert r.status_code == 200
    assert engine.cfg.url == "http://remote-host:12345"

    engine.cfg.update(**original)


def test_provider_switch_autofix_models(client, monkeypatch):
    import app as app_module

    engine = app_module.engine
    original = engine.cfg.to_dict()
    monkeypatch.setattr(engine, "_RAGEngine__init_backend", lambda: True)
    monkeypatch.setattr(engine, "_RAGEngine__check_backend", lambda: None)

    engine.status_backend = True
    engine.backend_models = ["lms-a", "lms-emb"]
    engine.backend_models_thinking = ["lms-a"]
    engine.backend_models_embed = ["lms-emb"]
    engine.cfg.update(
        provider="ollama", url="http://127.0.0.1:11434",
        llm="qwen3.5:4b", llm_embed="bge-m3:latest", llm_keywords="qwen3.5:4b",
    )

    # Модели, которых нет у нового провайдера, должны замениться автоматически.
    r = client.post("/rag/provider", json={"provider": "lmstudio"})
    assert r.status_code == 200
    assert engine.cfg.llm == "lms-a"
    assert engine.cfg.llm_keywords == "lms-a"
    assert engine.cfg.llm_embed == "lms-emb"

    # Явно выбранные модели не перезаписываются.
    engine.update_config(provider="ollama", llm="manual-model")
    assert engine.cfg.llm == "manual-model"
    assert engine.cfg.llm_keywords == "lms-a"

    engine.cfg.update(**original)


def test_provider_switch_autofix_skipped_when_backend_down(client, monkeypatch):
    import app as app_module

    engine = app_module.engine
    original = engine.cfg.to_dict()
    monkeypatch.setattr(engine, "_RAGEngine__init_backend", lambda: True)
    monkeypatch.setattr(engine, "_RAGEngine__check_backend", lambda: None)
    engine.status_backend = False

    engine.cfg.update(provider="ollama", llm="my-model")
    r = client.post("/rag/provider", json={"provider": "lmstudio"})
    assert r.status_code == 200
    assert engine.cfg.llm == "my-model"

    engine.cfg.update(**original)


def test_provider_set_invalid(client):
    r = client.post("/rag/provider", json={"provider": "vllm"})
    assert r.status_code == 400


def test_models_endpoint(client):
    r = client.get("/rag/models")
    assert r.status_code == 200
    data = r.get_json()
    assert "provider" in data
    assert "status_backend" in data
    assert "models" in data


def test_parse_endpoint_bad_path(client):
    r = client.post("/rag/parse", json={"file_path": r"Z:\nope.docx"})
    assert r.status_code == 404


def test_parse_endpoint_no_path(client):
    r = client.post("/rag/parse", json={})
    assert r.status_code == 400


def test_parse_endpoint_real_file(client, out_dir):
    target = out_dir / "#20-2026.02.18-О реорганизации работы отдела.docx"
    r = client.post("/rag/parse", json={"file_path": str(target)})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["page_count"] > 0
    assert "20" in data["content"]


def test_index_status(client):
    r = client.get("/rag/index/status")
    assert r.status_code == 200
    assert "is_syncing" in r.get_json()


def test_parse_stream(client, out_dir):
    target = out_dir / "#20-2026.02.18-О реорганизации работы отдела.docx"
    r = client.post(
        "/rag/parse/stream",
        json={"file_path": str(target)},
        buffered=True,
    )
    assert r.status_code == 200
    assert r.content_type.startswith("text/event-stream")
    chunks = []
    for line in r.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            chunks.append(json.loads(line[6:]))
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["page_count"] > 0
    assert any(c["type"] == "chunk" for c in chunks)


# ---------------------------------------------------------------------------
#  API для внешних агентов
# ---------------------------------------------------------------------------

def test_agent_stream_missing_prompt(client):
    r = client.post("/rag/agent/stream", json={})
    assert r.status_code == 400
    assert "prompt" in r.get_json()["error"]


def test_agent_stream_without_index(client):
    """Если индекс не готов — корректный 503."""
    r = client.post("/rag/agent/stream", json={"prompt": "гарантия"})
    assert r.status_code == 503
    assert "error" in r.get_json()


def test_agent_stream_emits_events(client, monkeypatch):
    """Поток агента отдаёт token/sources/done (SSE)."""
    import app as app_module

    engine = app_module.engine

    # Подменяем генератор, чтобы не ходить в реальную сеть/LLM.
    calls = {}

    def fake_agent_stream(prompt, system_prompt=None, top_k=None, temperature=None):
        calls["prompt"] = prompt
        calls["system_prompt"] = system_prompt
        calls["top_k"] = top_k
        calls["temperature"] = temperature
        yield {
            "type": "sources",
            "data": [{"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.9}],
        }
        yield {"type": "token", "data": "Ответ: "}
        yield {"type": "token", "data": "тест"}
        yield {
            "type": "done",
            "answer": "Ответ: тест",
            "sources": [{"file_name": "a.doc", "file_path": "C:\\a.doc", "score": 0.9}],
            "prompt": prompt,
        }

    monkeypatch.setattr(engine, "agent_stream", fake_agent_stream)
    engine.is_initialized = True
    engine.index = object()

    r = client.post(
        "/rag/agent/stream",
        json={
            "prompt": "Расскажи про гарантию",
            "system_prompt": "Будь краток.",
            "top_k": 5,
            "temperature": 0.3,
        },
        buffered=True,
    )
    assert r.status_code == 200
    assert r.content_type.startswith("text/event-stream")

    events = []
    for line in r.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    types = [e["type"] for e in events]
    assert types == ["sources", "token", "token", "done"]
    assert "".join(e.get("data", "") for e in events if e["type"] == "token") == "Ответ: тест"
    assert events[-1]["type"] == "done"
    assert events[-1]["answer"] == "Ответ: тест"
    assert events[-1]["sources"][0]["file_name"] == "a.doc"

    assert calls["prompt"] == "Расскажи про гарантию"
    assert calls["system_prompt"] == "Будь краток."
    assert calls["top_k"] == 5
    assert calls["temperature"] == 0.3