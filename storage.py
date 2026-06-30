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
_awaiting_contact: set[int] = set()
_new_client_sent: set[int] = set()
_last_amount_months: dict[int, tuple] = {}
_language_lock: dict[int, str] = {}
_pending_amount: dict[int, tuple] = {}  # (amount, rate_or_None)
_credit_rate: dict[int, float] = {}


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


def set_awaiting_contact(chat_id: int, amount: float, months: int) -> None:
    _awaiting_contact.add(chat_id)
    _last_amount_months[chat_id] = (amount, months)


def is_awaiting_contact(chat_id: int) -> bool:
    return chat_id in _awaiting_contact


def clear_awaiting_contact(chat_id: int) -> None:
    _awaiting_contact.discard(chat_id)


def get_last_amount_months(chat_id: int):
    return _last_amount_months.get(chat_id)


def was_new_client_reported(chat_id: int) -> bool:
    return chat_id in _new_client_sent


def mark_new_client_reported(chat_id: int) -> None:
    _new_client_sent.add(chat_id)


def get_language_lock(chat_id: int) -> str | None:
    return _language_lock.get(chat_id)


def set_language_lock_if_absent(chat_id: int, lock: str) -> None:
    if chat_id not in _language_lock:
        _language_lock[chat_id] = lock


def set_pending_amount(chat_id: int, amount: float, rate: float | None) -> None:
    _pending_amount[chat_id] = (amount, rate)


def get_pending_amount(chat_id: int):
    return _pending_amount.get(chat_id)


def clear_pending_amount(chat_id: int) -> None:
    _pending_amount.pop(chat_id, None)


def set_credit_rate_if_absent(chat_id: int, rate: float) -> None:
    if chat_id not in _credit_rate:
        _credit_rate[chat_id] = rate


def get_credit_rate(chat_id: int) -> float | None:
    return _credit_rate.get(chat_id)
