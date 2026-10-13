"""Ограничения использования по расписанию: хранение и оценка на сервере ядра.

Список хранится в settings.json (Settings.usage_restrictions) как список
dict: {id, days, start_time, end_time, message, active}.
Дни: 0=Пн … 6=Вс (как datetime.weekday()). start == end — весь день.
Диапазон через полночь (например 22:00–06:00) поддерживается.
"""
import re
from datetime import datetime

DEFAULT_BLOCK_MESSAGE = "Доступ к системе временно ограничен по расписанию."

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _to_minutes(hhmm: str):
    m = TIME_RE.match((hhmm or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def restriction_applies_now(item: dict, now: datetime = None) -> bool:
    """True, если ограничение действует в момент `now` (локальное время сервера)."""
    if not item.get("active"):
        return False
    now = now or datetime.now()
    days = item.get("days") or []
    if now.weekday() not in days:
        return False

    start = _to_minutes(item.get("start_time"))
    end = _to_minutes(item.get("end_time"))
    if start is None or end is None:
        return False

    cur = now.hour * 60 + now.minute
    if start == end:
        return True  # весь день
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end  # через полночь


def validate_payload(data: dict, partial: bool = False):
    """Валидация payload расписания. Возвращает (values, error)."""
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
            if not TIME_RE.match(val):
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


def next_id(items: list) -> int:
    return max((int(i.get("id") or 0) for i in items), default=0) + 1


def schedule_response(items: list, now: datetime = None) -> dict:
    """Ответ API: серверное время + список ограничений с applies_now."""
    now = now or datetime.now()
    return {
        "server_time": now.isoformat(timespec="seconds"),
        "server_time_hm": now.strftime("%H:%M"),
        "weekday": now.weekday(),
        "restrictions": [
            {**item, "applies_now": restriction_applies_now(item, now)}
            for item in items
        ],
    }
