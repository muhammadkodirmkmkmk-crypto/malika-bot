import requests
from config import TELEGRAM_API_URL


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        import json
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(
        f"{TELEGRAM_API_URL}/sendMessage",
        json=payload,
        timeout=15,
    )


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    try:
        requests.post(
            f"{TELEGRAM_API_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def send_typing(chat_id: int) -> None:
    """Показывает клиенту индикатор 'печатает...' в Telegram."""
    try:
        requests.post(
            f"{TELEGRAM_API_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except requests.RequestException:
        pass


def send_location(chat_id: int, latitude: float, longitude: float) -> None:
    try:
        requests.post(
            f"{TELEGRAM_API_URL}/sendLocation",
            json={"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
            timeout=10,
        )
    except Exception:
        pass


def set_webhook(url: str) -> dict:
    resp = requests.post(f"{TELEGRAM_API_URL}/setWebhook", json={"url": url}, timeout=15)
    return resp.json()
