import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


def config_dir() -> Path:
    """Каталог конфигурации: рядом с exe в frozen-сборке, иначе рядом с модулем."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


@dataclass
class Settings:
    """Конфигурация RAG-движка. Хранится в settings.json рядом с модулем."""

    # Провайдер инференса: "ollama" | "lmstudio"
    provider: str = "ollama"

    # Параметры индекса/чанков
    context_window: int = 4096
    chunk_size: int = 256
    chunk_overlap: int = 50
    similarity_top_k: int = 10
    page_limit: int = 10          # макс. кол-во страниц документа
    size_limit_mb: int = 5        # макс. размер файла в МБ
    embedding_dim: int = 768      # размерность векторной модели

    # Модели
    llm: str = "qwen3:4b"
    llm_embed: str = "nomic-embed-text-v2-moe:latest"
    llm_keywords: str = "llama3.2:3b"

    # Адрес API провайдера (Ollama: http://host:11434, LM Studio: http://host:1234/v1)
    # Дефолт — локальный Ollama (согласован с providers.DEFAULT_URLS).
    url: str = "http://127.0.0.1:11434"
    # API-ключ (обязателен для некоторых провайдеров; Ollama/LM Studio local — можно любой)
    api_key: str = ""

    # Папки для сканирования
    sync_folders: list = field(default_factory=list)

    def __post_init__(self) -> None:
        _config_path = config_dir() / "settings.json"
        if not _config_path.exists():
            return
        try:
            with _config_path.open("r", encoding="utf-8") as f:
                data: dict = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[Settings] Ошибка чтения {_config_path}: {exc}")
            return
        for k, v in data.items():
            if k in self.__dataclass_fields__:
                setattr(self, k, v)

    def save(self) -> None:
        target = config_dir() / "settings.json"
        temp = target.with_suffix(".tmp")
        try:
            with temp.open("w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4, sort_keys=True, ensure_ascii=False)
            temp.replace(target)
        except OSError as exc:
            print(f"[Settings] Ошибка сохранения {target}: {exc}")
            raise

    def to_dict(self) -> dict:
        return asdict(self)

    def update(self, **kwargs) -> dict:
        """Обновляет поля конфига. Возвращает список изменённых ключей."""
        changed = []
        for k, v in kwargs.items():
            if k not in self.__dataclass_fields__:
                continue
            if getattr(self, k) != v:
                setattr(self, k, v)
                changed.append(k)
        if changed:
            self.save()
        return changed
