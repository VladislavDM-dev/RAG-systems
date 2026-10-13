"""Конфигурация приложения."""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_or_create_secret() -> str:
    env_file = os.environ.get("SECRET_KEY_FILE")
    if env_file:
        secret_path = env_file
        os.makedirs(os.path.dirname(env_file), exist_ok=True)
    else:
        secret_path = os.path.join(BASE_DIR, "data", "secret_key")
        os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    if os.path.isfile(secret_path):
        key = open(secret_path, "r", encoding="utf-8").read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    try:
        with open(secret_path, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError:
        pass
    return key


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or _load_or_create_secret()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'data', 'app.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    RAG_API_URL = os.environ.get("RAG_API_URL", "http://127.0.0.1:11455/rag")
    PORT = int(os.environ.get("PORT", 80))

    MEMO_TEMPLATE_DIR = os.environ.get(
        "MEMO_TEMPLATE_DIR",
        os.path.join(BASE_DIR, "..", "docx_templates"),
    )

    OPEN_REGISTRATION = os.environ.get("OPEN_REGISTRATION", "true").lower() == "true"
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")

    MEMO_JS_VERSION = "20261013-02"

    SYSTEM_PROMPT_RAG = (
        "Ты — RAG-ассистент, отвечающий на основе предоставленных документов. "
        "Отвечай на вопрос, опираясь только на информацию из контекста ниже. "
        "Дай РАЗВЁРНУТЫЙ и подробный ответ: раскрой тему из документа максимально полно, "
        "приведи все релевантные факты, цифры, условия и детали, которые есть в контексте, "
        "структурируй ответ абзацами и, где уместно, списками. "
        "Не выдумывай факты и не добавляй информацию, которой нет в контексте. "
        "Если в контексте нет нужных данных, честно скажи, что информации нет."
    )

    SYSTEM_PROMPT_MEMO = (
        "Ты — RAG-ассистент, который составляет официальную служебную записку "
        "на основе предоставленных документов. "
        "Оформи текст как СЛУЖЕБНУЮ ЗАПИСКУ: в начале — адресат (Кому), составитель (От), "
        "заголовок с темой, затем основная часть с развёрнутым изложением предмета записки "
        "(факты, цифры, даты, реквизиты документов из контекста), в конце — вывод и предложение. "
        "Стиль официально-деловой, на русском языке, с абзацами. "
        "Опирайся ТОЛЬКО на информацию из контекста ниже; "
        "не выдумывай факты и не добавляй детали, которых нет в контексте. "
        "Если нужных данных нет, честно укажи, какой информации недостаёт."
    )

    COMMAND_CREATE = "/create"

    SYSTEM_PROMPT_MEMO_VARIANTS = (
        "Ты — помощник, который генерирует варианты текста служебной записки. "
        "На основе заданной темы и предоставленных документов возвращает ОДИН JSON-объект: "
        "{\"variants\": [\"текст_варианта_1\", \"текст_варианта_2\", ...], \"sources\": [{\"file_name\": ..., \"file_path\": ...}]} "
        "с 3–5 кратких вариантов (шапка + основная часть + подпись). "
        "Стиль официально-деловой, на русском языке. "
        "Если документов недостаточно — сгенерируй шаблонные фразы, пометив их. "
        "Не добавляй ничего, кроме JSON."
    )

    SYSTEM_PROMPT_MEMO_LIST = (
        "Ты — RAG-ассистент, перечисляющий служебные записки из индекса. "
        "На основе вопроса пользователя выдай список найденных служебных записок с заголовками и краткими описаниями. "
        "Список форматируй нумерованным списком, в конце укажи количество. "
        "Отвечай только по документам из контекста; если документов нет — напиши об этом."
    )
