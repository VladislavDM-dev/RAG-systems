"""Расписание ограничений использования: проверка запрета по дням и времени."""
import json
import re
from datetime import datetime

from models import UsageRestriction

DEFAULT_BLOCK_MESSAGE = "Доступ к системе временно ограничен по расписанию."

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _to_minutes(hhmm: str):
    m = TIME_RE.match((hhmm or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def restriction_applies_now(restriction: UsageRestriction, now: datetime = None) -> bool:
    """True, если ограничение действует в момент `now` (локальное время сервера).

    Дни: 0=Пн … 6=Вс (как datetime.weekday()). start == end — весь день.
    Диапазон через полночь (например 22:00–06:00) поддерживается.
    """
    if not restriction.active:
        return False
    now = now or datetime.now()
    try:
        days = json.loads(restriction.days_json or "[]")
    except ValueError:
        return False
    if now.weekday() not in days:
        return False

    start = _to_minutes(restriction.start_time)
    end = _to_minutes(restriction.end_time)
    if start is None or end is None:
        return False

    cur = now.hour * 60 + now.minute
    if start == end:
        return True  # весь день
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end  # через полночь


def get_restriction_message(user=None):
    """Текст блокировки, если сейчас действует запрет, иначе None.

    Администраторы не блокируются (им нужен доступ для управления).
    """
    if user is not None and getattr(user, "is_admin", False):
        return None
    now = datetime.now()
    for r in UsageRestriction.query.filter_by(active=True).all():
        if restriction_applies_now(r, now):
            return (r.message or "").strip() or DEFAULT_BLOCK_MESSAGE
    return None
