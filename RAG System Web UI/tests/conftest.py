"""Фикстуры для тестов нового Web UI (Flask + SQLite + Flask-Login)."""
import os
import re
import tempfile

# Окружение ДО импорта app: изолированная БД, тестовый секрет, недостижимый RAG API.
_TMP = tempfile.mkdtemp(prefix="rag_ui_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "app.db")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["RAG_API_URL"] = "http://127.0.0.1:1/rag"

import pytest

from app import app
from extensions import db
from models import User
from api_client import RAGClient


class FakeRAG(RAGClient):
    """Стаб RAG API: все запросы возвращают безопасные значения без сети."""

    def __init__(self):
        super().__init__("http://127.0.0.1:1/rag", timeout=1)

    def index_status(self):
        return {"is_syncing": False, "initialized": True, "status": "ok", "progress": 100}

    def health(self):
        return {"status": "ok"}

    def info(self):
        return {"status_backend": True, "provider": "test"}

    def engine_status(self):
        return {"version": "test", "document_count": 0, "index_updated": "—",
                "is_initialized": True, "is_syncing": False, "status": "ok", "progress": 0}

    def get_config(self):
        return {"provider": "test", "url": "http://127.0.0.1:1"}

    def list_models(self):
        return {"models": {}}

    def get_folders(self):
        return []

    def parse_file(self, file_path):
        return {"ok": False, "error": "stub"}

    def memos(self, prompt, temperature=0.2, page_size=30, max_pages=15):
        return {"ok": True, "total": 0, "documents": []}


def _csrf_token(client):
    html = client.get("/login").get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token не найден на странице /login"
    return match.group(1)


@pytest.fixture()
def client():
    app.rag = FakeRAG()
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(username="admin", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def logged_client(client):
    token = _csrf_token(client)
    resp = client.post("/login", data={
        "username": "admin",
        "password": "admin123",
        "csrf_token": token,
    }, follow_redirects=True)
    assert resp.status_code == 200
    return client