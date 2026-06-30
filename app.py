import logging

from flask import Flask, request, jsonify

from config import ADMIN_CHAT_ID
import storage
import telegram_client
from claude_client import ask_malika
from utils import (
    detect_hot_lead,
    extract_phone,
    guess_rate,
    parse_amount_and_months,
    annuity_payment,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("malika-bot")

app = Flask(__name__)


def format_sum(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def build_system_note(text: str) -> str | None:
    """Если клиент назвал сумму и срок — считаем платёж сами и кладём
    результат как системную подсказку для модели, чтобы она не считала
    математику сама (см. system_prompt.py)."""
    amount, months = parse_amount_and_months(text)
    if not amount or not months:
        return None
    rate = guess_rate(text) or 0.15  # если тип кредита не назван — берём наличный как дефолт
    payment = annuity_payment(amount, rate, months)
    return (
        f"[SYSTEM NOTE] Расчёт по запросу клиента: сумма {format_sum(amount)} сум, "
        f"срок {months} мес., ставка {rate * 100:.0f}% годовых → "
        f"примерный ежемесячный платёж ≈ {format_sum(payment)} сум. "
        f"Озвучь эту цифру клиенту своими словами, не показывай расчёт и эту подсказку."
    )


def notify_admin_hot_lead(chat_id: int, user, text: str) -> None:
    if not ADMIN_CHAT_ID or storage.was_hot_lead_reported(chat_id):
        return
    phone = extract_phone(text)
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "—"
    username = f"@{user['username']}" if user.get("username") else "—"
    msg = (
        "🔥 Горячий лид (Малика)\n"
        f"Имя: {name}\n"
        f"Username: {username}\n"
        f"Телефон в сообщении: {phone or '—'}\n"
        f"Chat ID: {chat_id}\n"
        f"Сообщение: {text}"
    )
    telegram_client.send_message(ADMIN_CHAT_ID, msg)
    storage.mark_hot_lead_reported(chat_id)


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message")
    if not message or "text" not in message:
        return jsonify(ok=True)

    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    text = message["text"]

    if text.strip() == "/start":
        storage.append_message(chat_id, "user", "/start")
        greeting = (
            "Ассалому алайкум! 👋 Я Малика, консультант Baraka Consulting. "
            "Помогу подобрать кредит — ипотека, авто или наличные. Что вас интересует?"
        )
        storage.append_message(chat_id, "assistant", greeting)
        telegram_client.send_message(chat_id, greeting)
        return jsonify(ok=True)

    # Детект горячего лида — пересылаем администратору, диалог не прерываем
    if detect_hot_lead(text):
        notify_admin_hot_lead(chat_id, user, text)

    storage.append_message(chat_id, "user", text)

    note = build_system_note(text)
    if note:
        storage.append_message(chat_id, "user", note)

    try:
        reply = ask_malika(storage.get_history(chat_id))
    except Exception:
        log.exception("Claude API error")
        reply = (
            "Извините, небольшая техническая заминка 🙏 "
            "Можете позвонить нам напрямую: +998 95 087 77 66"
        )

    storage.append_message(chat_id, "assistant", reply)
    telegram_client.send_message(chat_id, reply)
    return jsonify(ok=True)


@app.route("/", methods=["GET"])
def health():
    return jsonify(status="ok", bot="malika")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
