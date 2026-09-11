import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# Корень проекта, чтобы импортировать app и rag_engine
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT.parent / "out"

sys.path.insert(0, str(PROJECT_ROOT))

SETTINGS_PATH = PROJECT_ROOT / "rag_engine" / "settings.json"


@pytest.fixture(scope="session", autouse=True)
def pin_settings():
    """Фиксируем канонический (дефолтный) settings.json на время прогона.

    Тесты меняют конфиг через Settings.update()/save() и через API.
    Чтобы прогоны были детерминированными независимо от истории, в начале
    сессии переписываем файл на дефолты кода, а после — восстанавливаем
    исходное содержимое пользователя.
    """
    original = SETTINGS_PATH.read_text(encoding="utf-8") if SETTINGS_PATH.exists() else None

    # Класс импортируется без чтения файла: на старте файл удалён
    from rag_engine.config import Settings

    SETTINGS_PATH.unlink(missing_ok=True)
    defaults = Settings()
    SETTINGS_PATH.write_text(
        json.dumps(defaults.to_dict(), ensure_ascii=False, indent=4, sort_keys=True),
        encoding="utf-8",
    )

    yield

    if original is not None:
        SETTINGS_PATH.write_text(original, encoding="utf-8")
    else:
        SETTINGS_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def out_dir() -> Path:
    return OUT_DIR


@pytest.fixture(scope="session")
def workspace(tmp_path_factory) -> Path:
    """Изолированная рабочая папка, чтобы .cache не засорял проект."""
    tmp = tmp_path_factory.mktemp("rag_wspace")
    return tmp


@pytest.fixture(scope="session")
def client(workspace, pin_settings):
    """Flask test client. Меняем cwd во временную папку ДО импорта app,
    затем, после завершения тестов, восстанавливаем исходный каталог."""
    cwd_backup = os.getcwd()
    os.chdir(workspace)
    try:
        import app as app_module

        app_module.app.config["TESTING"] = True
        yield app_module.app.test_client()
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(workspace, ignore_errors=True)