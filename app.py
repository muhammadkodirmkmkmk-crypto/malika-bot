import logging

from flask import Flask, request, jsonify

from config import ADMIN_CHAT_ID, OWNER_CHAT_ID
import storage
import telegram_client
from claude_client import ask_malika
from utils import (
    detect_hot_lead,
    extract_phone,
    guess_rate,
    parse_amount_and_months,
    annuity_payment,
    looks_like_contact_info,
    strip_markdown_asterisks,
    detect_language_lock,
    LANGUAGE_LOCK_LABELS,
    build_payment_message,
    format_sum,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("malika-bot")

app = Flask(__name__)

DEFAULT_LANG = "uz_latin"  # если язык ещё не определён однозначно


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


def notify_owner_new_client(chat_id: int, user, contact_text: str) -> None:
    if not OWNER_CHAT_ID or storage.was_new_client_reported(chat_id):
        return
    username = f"@{user['username']}" if user.get("username") else "—"
    amount_months = storage.get_last_amount_months(chat_id)
    if amount_months:
        amount, months = amount_months
        credit_line = f"Запрос: {format_sum(amount)} сум на {months} мес."
    else:
        credit_line = "Запрос: —"
    msg = (
        "🆕 Новый клиент (Малика)\n"
        f"Контактные данные от клиента: {contact_text}\n"
        f"{credit_line}\n"
        f"Telegram username: {username}\n"
        f"Chat ID: {chat_id}"
    )
    telegram_client.send_message(OWNER_CHAT_ID, msg)
    storage.mark_new_client_reported(chat_id)


def update_language_lock(chat_id: int, text: str) -> str:
    """Определяет/фиксирует язык диалога, возвращает текущий действующий язык."""
    lock = detect_language_lock(text)
    if lock:
        storage.set_language_lock_if_absent(chat_id, lock)
    return storage.get_language_lock(chat_id) or DEFAULT_LANG


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
        telegram_client.send_typing(chat_id)
        greeting = (
            "Ассалому алайкум! 👋 Я Малика, консультант Baraka Consulting. "
            "Помогу подобрать кредит — ипотека, авто или наличные. Что вас интересует?"
        )
        storage.append_message(chat_id, "assistant", greeting)
        telegram_client.send_message(chat_id, greeting)
        return jsonify(ok=True)

    # Если ранее попросили контакты — проверяем, похоже ли это сообщение на них
    if storage.is_awaiting_contact(chat_id) and looks_like_contact_info(text):
        notify_owner_new_client(chat_id, user, text)
        storage.clear_awaiting_contact(chat_id)

    # Детект горячего лида — пересылаем администратору, диалог не прерываем
    if detect_hot_lead(text):
        notify_admin_hot_lead(chat_id, user, text)

    storage.append_message(chat_id, "user", text)
    current_lang = update_language_lock(chat_id, text)

    # Если клиент назвал сумму и срок — платёж считает и пишет код,
    # модель в этом шаге вообще не участвует (исключает любые "слитые" расчёты)
    amount, months = parse_amount_and_months(text)
    if amount and months:
        rate = guess_rate(text) or 0.15
        payment = annuity_payment(amount, rate, months)
        reply = build_payment_message(amount, months, payment, current_lang)
        storage.set_awaiting_contact(chat_id, amount, months)
        telegram_client.send_typing(chat_id)
        storage.append_message(chat_id, "assistant", reply)
        telegram_client.send_message(chat_id, reply)
        return jsonify(ok=True)

    telegram_client.send_typing(chat_id)

    dynamic_addendum = f"Язык/алфавит этого диалога зафиксирован: {LANGUAGE_LOCK_LABELS[current_lang]}. Отвечай только так."

    try:
        reply = ask_malika(storage.get_history(chat_id), dynamic_addendum=dynamic_addendum)
        reply = strip_markdown_asterisks(reply)
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
