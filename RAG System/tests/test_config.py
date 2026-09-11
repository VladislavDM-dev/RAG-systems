import json
from pathlib import Path

import pytest

from rag_engine.config import Settings

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "rag_engine" / "settings.json"


@pytest.fixture(autouse=True)
def clean_settings():
    """Изолируем конфиг-тесты от реального settings.json в пакете.

    Удаляем файл до теста (Settings() вернёт дефолты), в конце восстанавливаем.
    """
    original = _CONFIG_PATH.read_text(encoding="utf-8") if _CONFIG_PATH.exists() else None
    _CONFIG_PATH.unlink(missing_ok=True)
    yield
    if original is not None:
        _CONFIG_PATH.write_text(original, encoding="utf-8")
    else:
        _CONFIG_PATH.unlink(missing_ok=True)


def test_defaults():
    cfg = Settings()
    assert cfg.provider == "ollama"
    assert cfg.context_window == 4096
    assert cfg.chunk_size == 256
    assert cfg.chunk_overlap == 50
    assert cfg.similarity_top_k == 10
    assert cfg.embedding_dim == 768
    assert cfg.page_limit == 10
    assert cfg.size_limit_mb == 5
    assert cfg.sync_folders == []


def test_update_returns_changed(tmp_path):
    cfg = Settings()
    # Не даём конструктору прочитать реальный settings.json в пакете,
    # а тестируем чисто update().
    changed = cfg.update(chunk_size=512, llm_embed="x", unknown_field=123)
    assert set(changed) == {"chunk_size", "llm_embed"}
    assert cfg.chunk_size == 512
    assert cfg.llm_embed == "x"


def test_no_change_returns_empty():
    cfg = Settings()
    changed = cfg.update(provider="ollama", chunk_size=256)
    assert changed == []


def test_save_and_load_roundtrip():
    """Сохраняем конфиг, читаем новый экземпляр Settings и сравниваем."""
    cfg = Settings()
    cfg.provider = "lmstudio"
    cfg.chunk_size = 128
    cfg.context_window = 1000
    cfg.sync_folders = ["C:\\docs", "D:\\arh"]
    cfg.save()

    loaded = Settings()
    assert loaded.provider == "lmstudio"
    assert loaded.chunk_size == 128
    assert loaded.context_window == 1000
    assert loaded.sync_folders == ["C:\\docs", "D:\\arh"]


def test_to_dict_contains_expected_keys():
    keys = {
        "provider", "context_window", "chunk_size", "chunk_overlap",
        "similarity_top_k", "page_limit", "size_limit_mb", "embedding_dim",
        "llm", "llm_embed", "llm_keywords", "url", "api_key", "sync_folders",
    }
    assert keys <= set(Settings().to_dict().keys())