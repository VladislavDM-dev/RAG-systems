"""Ограничения использования: источник — ядро RAG (GET /rag/schedule).

Web UI не хранит расписание сам; при проверке запрета опрашивается ядро
(applies_now считает сервер ядра по своему локальному времени).
Администраторы не блокируются.
"""
from flask import current_app

DEFAULT_BLOCK_MESSAGE = "Доступ к системе временно ограничен по расписанию."


def get_restriction_message(user=None):
    """Текст блокировки из расписания ядра, если запрет действует сейчас, иначе None.

    Ошибки/недоступность ядра игнорируются (fail-open): без ядра чат
    всё равно неработоспособен, блокировать незачем.
    """
    if user is not None and getattr(user, "is_admin", False):
        return None
    try:
        data = current_app.rag.get_schedule()
    except Exception:
        return None
    for r in data.get("restrictions") or []:
        if r.get("active") and r.get("applies_now"):
            return (r.get("message") or "").strip() or DEFAULT_BLOCK_MESSAGE
    return None
