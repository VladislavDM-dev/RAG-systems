import pytest

from rag_engine.providers import (
    BaseProvider,
    LMStudioProvider,
    OllamaProvider,
    ProviderError,
    create_provider,
)


def test_factory_ollama():
    p = create_provider("ollama", "http://localhost:11434", "")
    assert isinstance(p, OllamaProvider)
    assert isinstance(p, BaseProvider)


def test_factory_lmstudio():
    p = create_provider("lmstudio", "http://localhost:1234/v1", "k")
    assert isinstance(p, LMStudioProvider)


def test_factory_lmstudio_aliases():
    for alias in ("lm-studio", "openai", "openailike"):
        assert isinstance(create_provider(alias, "http://x/v1"), LMStudioProvider)


def test_factory_case_insensitive():
    assert isinstance(create_provider("Ollama", "http://x"), OllamaProvider)


def test_factory_unknown_raises():
    with pytest.raises(ProviderError):
        create_provider("vllm", "http://x")


def test_provider_names():
    assert OllamaProvider("http://x").name == "ollama"
    assert LMStudioProvider("http://x").name == "lmstudio"


def test_is_available_gracefully_false():
    """Без работающего сервера is_available() возвращает False, не бросая."""
    p = OllamaProvider("http://127.0.0.1:1")
    assert p.is_available() is False


def test_default_urls_defined():
    from rag_engine.providers import DEFAULT_URLS

    assert DEFAULT_URLS["ollama"] == "http://127.0.0.1:11434"
    assert DEFAULT_URLS["lmstudio"] == "http://127.0.0.1:1234/v1"


def test_lmstudio_capabilities_detect_embedding():
    p = LMStudioProvider("http://127.0.0.1:1234/v1")
    assert p.capabilities("text-embedding-nomic-embed-text-v1.5", "embedding") is True
    assert p.capabilities("qwen3.8-4b-distill", "embedding") is False
    assert p.capabilities("qwen3.8-4b-distill", "thinking") is True
    assert p.capabilities("text-embedding-nomic-embed-text-v1.5", "thinking") is False