"""
Простое in-memory хранилище истории диалогов по chat_id.
Для продакшена при рестарте Railway история обнулится — это ок для
консультационного бота без БД, но при желании легко заменить
на Redis/Postgres, сохранив тот же интерфейс (get_history/append/reset).
"""

from collections import defaultdict
from config import HISTORY_LIMIT

_history: dict[int, list[dict]] = defaultdict(list)
_hot_lead_sent: set[int] = set()


def get_history(chat_id: int) -> list[dict]:
    return _history[chat_id]


def append_message(chat_id: int, role: str, content: str) -> None:
    _history[chat_id].append({"role": role, "content": content})
    if len(_history[chat_id]) > HISTORY_LIMIT:
        _history[chat_id] = _history[chat_id][-HISTORY_LIMIT:]


def was_hot_lead_reported(chat_id: int) -> bool:
    return chat_id in _hot_lead_sent


def mark_hot_lead_reported(chat_id: int) -> None:
    _hot_lead_sent.add(chat_id)
