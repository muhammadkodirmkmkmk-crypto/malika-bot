import requests
from config import TELEGRAM_API_URL


def send_message(chat_id: int, text: str) -> None:
    requests.post(
        f"{TELEGRAM_API_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )


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


def set_webhook(url: str) -> dict:
    resp = requests.post(f"{TELEGRAM_API_URL}/setWebhook", json={"url": url}, timeout=15)
    return resp.json()
