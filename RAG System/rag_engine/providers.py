"""Абстракция над провайдерами инференса: Ollama и LM Studio (OpenAI-совместимый).

Единый интерфейс для:
- настройки LLM и эмбеддингов LlamaIndex;
- извлечения ключевых слов;
- получения списка моделей и проверки доступности.
"""
from typing import List, Optional

import httpx

# Таймауты HTTP-клиентов бэкендов. Пробы (list_models/capabilities) должны
# быстро отваливаться на недоступном/нелокальном адресе — иначе смена
# провайдера/моделей через админку зависает на десятки секунд (дефолтные
# таймауты openai/ollama достигают 600с).
_PROBE_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=3.0)
_PROBE_MAX_RETRIES = 1
# Реальная генерация (ключевые слова) может быть долгой — щедрый таймаут.
_GENERATE_TIMEOUT = 600.0


class ProviderError(RuntimeError):
    pass


# Адреса по умолчанию для каждого провайдера.
# Используются при смене провайдера, если url вручную не указывался.
DEFAULT_URLS = {
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://127.0.0.1:1234/v1",
}

# Подстроки имён моделей, которые считаются эмбеддинговыми
# (нужны для LM Studio, где нет нативного списка capabilities).
_EMBED_MODEL_HINTS = (
    "embed",
    "bge",
    "mxbai",
    "gte-",
    "e5-base",
    "e5-large",
    "e5-small",
    "nomic-embed",
)


def _is_embedding_model(model: str) -> bool:
    return any(h in model.lower() for h in _EMBED_MODEL_HINTS)


class BaseProvider:
    name = "base"

    def __init__(self, url: str, api_key: str = ""):
        self.url = url
        self.api_key = api_key

    # --- LlamaIndex объекты -------------------------------------------------
    def build_llm(self, model: str, context_window: int, temperature: float):
        raise NotImplementedError

    def build_embed_model(self, model: str):
        raise NotImplementedError

    # --- Служебные операции -------------------------------------------------
    def generate_text(self, model: str, prompt: str) -> str:
        """Однопроходная генерация текста (для ключевых слов)."""
        raise NotImplementedError

    def list_models(self) -> List[str]:
        raise NotImplementedError

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
#  Ollama (native API)
# ---------------------------------------------------------------------------
class OllamaProvider(BaseProvider):
    name = "ollama"

    def build_llm(self, model: str, context_window: int, temperature: float):
        from llama_index.llms.ollama import Ollama

        return Ollama(
            model=model,
            request_timeout=600.0,
            base_url=self.url,
            temperature=temperature,
            context_window=context_window,
            streaming=True,
            system="Ты полезный ассистент. Всегда отвечай на русском языке.",
        )

    def build_embed_model(self, model: str):
        from llama_index.embeddings.ollama import OllamaEmbedding

        return OllamaEmbedding(
            model_name=model,
            base_url=self.url,
            embed_batch_size=10,
        )

    def _client(self, timeout):
        import ollama

        return ollama.Client(host=self.url, timeout=timeout)

    def generate_text(self, model: str, prompt: str) -> str:
        client = self._client(_GENERATE_TIMEOUT)
        response = client.generate(model=model, prompt=prompt)
        return response["response"]

    def list_models(self) -> List[str]:
        client = self._client(_PROBE_TIMEOUT)
        return [m["model"] for m in client.list()["models"]]

    def capabilities(self, model: str, cap: str) -> bool:
        client = self._client(_PROBE_TIMEOUT)
        try:
            details = client.show(model)
            return bool(details and cap in details.get("capabilities", []))
        except Exception:
            return False


# ---------------------------------------------------------------------------
#  LM Studio / OpenAI-совместимые
# ---------------------------------------------------------------------------
class LMStudioProvider(BaseProvider):
    name = "lmstudio"

    def build_llm(self, model: str, context_window: int, temperature: float):
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=model,
            api_base=self.url,
            api_key=self.api_key or "lm-studio",
            temperature=temperature,
            context_window=context_window,
            streaming=True,
            timeout=600.0,
            is_chat_model=True,
            system_prompt="Ты полезный ассистент. Всегда отвечай на русском языке.",
        )

    def build_embed_model(self, model: str):
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model_name=model,
            api_base=self.url,
            api_key=self.api_key or "lm-studio",
            embed_batch_size=10,
        )

    def _openai_client(self, timeout, max_retries=_PROBE_MAX_RETRIES):
        from openai import OpenAI

        return OpenAI(
            base_url=self.url,
            api_key=self.api_key or "lm-studio",
            timeout=timeout,
            max_retries=max_retries,
        )

    def generate_text(self, model: str, prompt: str) -> str:
        client = self._openai_client(_GENERATE_TIMEOUT)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def list_models(self) -> List[str]:
        client = self._openai_client(_PROBE_TIMEOUT)
        return [m.id for m in client.models.list().data]

    def capabilities(self, model: str, cap: str) -> bool:
        # У OpenAI-совместимых API нет нативного списка capabilities;
        # распознаём эмбеддинговые модели по имени, остальные считаем LLM.
        is_embed = _is_embedding_model(model)
        if cap == "embedding":
            return is_embed
        return not is_embed


def create_provider(provider: str, url: str, api_key: str = "") -> BaseProvider:
    """Фабрика провайдеров."""
    p = (provider or "ollama").lower().strip()
    if p == "ollama":
        return OllamaProvider(url, api_key)
    if p in ("lmstudio", "lm-studio", "openai", "openailike"):
        return LMStudioProvider(url, api_key)
    raise ProviderError(f"Неизвестный провайдер: {provider}. Доступно: ollama, lmstudio")
