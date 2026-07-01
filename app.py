import logging

from flask import Flask, request, jsonify

from config import OWNER_CHAT_ID, OWNER_CHAT_ID_2
import storage
import telegram_client
from claude_client import ask_malika
from utils import (
    guess_rate,
    parse_explicit_rate,
    parse_amount_and_months,
    parse_amount,
    parse_months,
    parse_bare_years_answer,
    annuity_payment,
    looks_like_contact_info,
    strip_markdown_asterisks,
    LANGUAGE_LOCK_LABELS,
    build_payment_message,
    format_sum,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("malika-bot")

app = Flask(__name__)

# ─── Офис Baraka Consulting ───────────────────────────────────────────────────
OFFICE_LAT  = 41.2995   # Ташкент, Учтепинский район
OFFICE_LON  = 69.2401
OFFICE_ADDR = {
    "uz_latin":   "📍 Manzil: Toshkent, Uchtepa tumani\n📞 +998 95 087 77 66\n🕐 Du-Sha, 9:00–18:00",
    "uz_cyrillic":"📍 Манзил: Тошкент, Учтепа тумани\n📞 +998 95 087 77 66\n🕐 Ду-Ша, 9:00–18:00",
    "ru":         "📍 Адрес: Ташкент, Учтепинский район\n📞 +998 95 087 77 66\n🕐 Пн-Сб, 9:00–18:00",
}

LOCATION_KEYWORDS = [
    "локаци", "адрес", "где вы", "где находит", "офис",
    "manzil", "lokatsiya", "qayerda", "joylashuv", "ofis",
    "манзил", "қаерда",
]

def is_location_request(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in LOCATION_KEYWORDS)


# ─── Кнопки выбора языка ─────────────────────────────────────────────────────

LANG_KEYBOARD = {
    "inline_keyboard": [[
        {"text": "O'zbek tili 🇺🇿", "callback_data": "lang|uz_latin"},
        {"text": "Русский язык 🇷🇺",  "callback_data": "lang|ru"},
    ]]
}

LANG_QUESTION = "Assalomu alaykum! 👋\n\nQaysi tilda muloqot qilishni afzal ko'rasiz?\nНа каком языке вам удобнее общаться?"

GREETINGS = {
    "uz_latin": (
        "Assalomu alaykum! 👋 Men Odilbek — Baraka Consulting maslahatchisiman.\n"
        "Kredit tanlashda yordam beraman: ipoteka, avtokredit yoki naqd pul.\n"
        "Qaysi biri sizni qiziqtiradi?"
    ),
    "uz_cyrillic": (
        "Ассалому алайкум! 👋 Мен Одилбек — Baraka Consulting маслаҳатчисиман.\n"
        "Кредит танлашда ёрдам бераман: ипотека, автокредит ёки нақд пул.\n"
        "Қайси бири сизни қизиқтиради?"
    ),
    "ru": (
        "Здравствуйте! 👋 Я Одилбек, консультант Baraka Consulting.\n"
        "Помогу подобрать кредит — ипотека, авто или наличные.\n"
        "Что вас интересует?"
    ),
}


# ─── Уведомления владельцам ───────────────────────────────────────────────────

def send_lead_to_owner(chat_id: int, user, contact_text: str) -> None:
    if not OWNER_CHAT_ID or storage.was_new_client_reported(chat_id):
        return
    username = f"@{user['username']}" if user.get("username") else "—"
    amount_months = storage.get_last_amount_months(chat_id)
    credit_line = f"{format_sum(amount_months[0])} so'm, {amount_months[1]} oy" if amount_months else "—"
    msg = (
        "🆕 Yangi mijoz — Odilbek boti\n\n"
        f"👤 Mijoz yuborgan ma'lumot:\n{contact_text}\n\n"
        f"💰 So'rov: {credit_line}\n"
        f"🔗 Telegram: {username}\n"
        f"🆔 Chat ID: {chat_id}"
    )
    telegram_client.send_message(OWNER_CHAT_ID, msg)
    telegram_client.send_message(OWNER_CHAT_ID_2, msg)
    storage.mark_new_client_reported(chat_id)


# ─── Обработчик callback (кнопки) ────────────────────────────────────────────

def handle_callback(data: dict) -> None:
    cb_data = data.get("data", "")
    chat_id = data["message"]["chat"]["id"]
    cb_id   = data["id"]

    if cb_data.startswith("lang|"):
        lang = cb_data.split("|", 1)[1]
        storage.set_language_lock(chat_id, lang)
        telegram_client.answer_callback_query(cb_id)
        greeting = GREETINGS.get(lang, GREETINGS["ru"])
        storage.append_message(chat_id, "assistant", greeting)
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, greeting)


# ─── Webhook ─────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}

    # Нажатие на кнопку выбора языка
    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return jsonify(ok=True)

    message = update.get("message")
    if not message or "text" not in message:
        return jsonify(ok=True)

    chat_id = message["chat"]["id"]
    user    = message.get("from", {})
    text    = message["text"]

    # /start — всегда сбрасываем и показываем выбор языка
    if text.strip() == "/start":
        storage._language_lock.pop(chat_id, None)  # сброс языка
        telegram_client.send_message(chat_id, LANG_QUESTION, reply_markup=LANG_KEYBOARD)
        return jsonify(ok=True)

    # Если язык ещё не выбран — напоминаем нажать кнопку
    if not storage.is_language_chosen(chat_id):
        telegram_client.send_message(chat_id, LANG_QUESTION, reply_markup=LANG_KEYBOARD)
        return jsonify(ok=True)

    current_lang = storage.get_language_lock(chat_id)

    # Если ранее попросили контакты — проверяем похоже ли ответ на них
    if storage.is_awaiting_contact(chat_id) and looks_like_contact_info(text):
        send_lead_to_owner(chat_id, user, text)
        storage.clear_awaiting_contact(chat_id)

    storage.append_message(chat_id, "user", text)

    # Запрос локации — отвечаем сразу, без модели
    if is_location_request(text):
        telegram_client.send_message(chat_id, OFFICE_ADDR.get(current_lang, OFFICE_ADDR["ru"]))
        telegram_client.send_location(chat_id, OFFICE_LAT, OFFICE_LON)
        return jsonify(ok=True)

    # Тип кредита — запоминаем на весь диалог
    rate_from_text = guess_rate(text)
    if rate_from_text:
        storage.set_credit_rate_if_absent(chat_id, rate_from_text)

    # Если клиент назвал сумму и срок — считаем сами (модель не участвует)
    amount, months = parse_amount_and_months(text)
    rate = rate_from_text if (amount and months) else None
    if not (amount and months):
        amt_only    = parse_amount(text)
        months_only = parse_months(text)
        pending     = storage.get_pending_amount(chat_id)
        if amt_only and not months_only:
            storage.set_pending_amount(chat_id, amt_only, rate_from_text)
        elif pending and (months_only or parse_bare_years_answer(text)):
            amount, rate = pending
            months = months_only or parse_bare_years_answer(text)
            storage.clear_pending_amount(chat_id)

    if amount and months:
        rate = rate or storage.get_credit_rate(chat_id) or 0.26
        payment = annuity_payment(amount, rate, months)
        reply = build_payment_message(amount, months, payment, current_lang, rate=rate)
        storage.set_awaiting_contact(chat_id, amount, months)
        telegram_client.send_typing(chat_id)
        storage.append_message(chat_id, "assistant", reply)
        telegram_client.send_message(chat_id, reply)
        return jsonify(ok=True)

    # Обычный диалог — передаём модели
    telegram_client.send_typing(chat_id)
    dynamic_addendum = (
        f"Язык этого диалога ЗАФИКСИРОВАН: {LANGUAGE_LOCK_LABELS[current_lang]}. "
        f"Отвечай ТОЛЬКО на этом языке и алфавите, без исключений, до конца разговора. "
        f"Твоё имя — Odilbek, не Malika."
    )
    try:
        reply = ask_malika(storage.get_history(chat_id), dynamic_addendum=dynamic_addendum)
        reply = strip_markdown_asterisks(reply)
    except Exception:
        log.exception("Claude API error")
        reply = "Извините, небольшая техническая заминка 🙏 Позвоните нам: +998 95 087 77 66"

    storage.append_message(chat_id, "assistant", reply)
    telegram_client.send_message(chat_id, reply)
    return jsonify(ok=True)


@app.route("/", methods=["GET"])
def health():
    return jsonify(status="ok", bot="odilbek")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
