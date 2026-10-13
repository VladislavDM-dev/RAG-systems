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
        self._schedule = []

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

    # --- Расписание (эмуляция ядра /rag/schedule) ---

    def get_schedule(self):
        from datetime import datetime
        now = datetime.now()
        items = []
        for r in self._schedule:
            applies = bool(r.get("active")) and now.weekday() in (r.get("days") or [])
            if applies:
                s, e = r.get("start_time"), r.get("end_time")
                if s != e:
                    cur = now.strftime("%H:%M")
                    applies = (s <= cur < e) if s < e else (cur >= s or cur < e)
            items.append({**r, "applies_now": applies})
        return {
            "server_time": now.isoformat(timespec="seconds"),
            "server_time_hm": now.strftime("%H:%M"),
            "weekday": now.weekday(),
            "restrictions": items,
        }

    def _schedule_validate(self, data, partial=False):
        import re
        time_re = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
        values = {}
        if not partial or "days" in data:
            days = data.get("days")
            if (not isinstance(days, list) or not days
                    or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days)):
                return None, "Поле 'days' — непустой список чисел 0..6 (0=Пн)"
            values["days"] = sorted(set(days))
        for field in ("start_time", "end_time"):
            if not partial or field in data:
                val = (data.get(field) or "").strip()
                if not time_re.match(val):
                    return None, f"Поле '{field}' — время в формате HH:MM"
                values[field] = val
        if not partial or "message" in data:
            msg = (data.get("message") or "").strip()
            if not msg:
                return None, "Поле 'message' обязательно — текст блокировки для пользователя"
            values["message"] = msg
        if "active" in data:
            values["active"] = bool(data.get("active"))
        return values, None

    def add_schedule(self, data):
        values, error = self._schedule_validate(data)
        if error:
            return {"error": error}
        rid = max((r["id"] for r in self._schedule), default=0) + 1
        self._schedule.append({"id": rid, "active": True, **values})
        return {"ok": True, **self.get_schedule()}

    def update_schedule(self, rid, data):
        values, error = self._schedule_validate(data, partial=True)
        if error:
            return {"error": error}
        for r in self._schedule:
            if r["id"] == rid:
                r.update(values)
                return {"ok": True, **self.get_schedule()}
        return {"error": "Ограничение не найдено"}

    def delete_schedule(self, rid):
        n = len(self._schedule)
        self._schedule = [r for r in self._schedule if r["id"] != rid]
        if len(self._schedule) == n:
            return {"error": "Ограничение не найдено"}
        return {"ok": True, **self.get_schedule()}


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