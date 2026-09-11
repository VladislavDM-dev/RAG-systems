import pytest
import tempfile
import os

import app as app_module
from app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Клиент с тестовой историей в отдельной папке и тестовым users.json."""
    data_dir = tmp_path / "data"
    users_file = tmp_path / "users.json"
    app_module.DATA_DIR = str(data_dir)
    app_module.USERS_FILE = str(users_file)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def auth_client(client):
    """Авторизованный клиент (session['user']='admin')."""
    with client.session_transaction() as sess:
        sess["user"] = "admin"
    return client