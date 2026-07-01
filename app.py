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
OFFICE_LAT  = 41.285384
OFFICE_LON  = 69.169782
OFFICE_ADDR = {
    "uz_latin":   "📍 Manzil: Toshkent, Uchtepa tumani\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📸 @baraka_consulting_uz\n🕐 Du-Sha, 9:00–18:00",
    "uz_cyrillic":"📍 Манзил: Тошкент, Учтепа тумани\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📸 @baraka_consulting_uz\n🕐 Ду-Ша, 9:00–18:00",
    "ru":         "📍 Адрес: Ташкент, Учтепинский район\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📸 @baraka_consulting_uz\n🕐 Пн-Сб, 9:00–18:00",
}

RATE_QUESTION = {
    "uz_latin":   "Qanday foiz stavkasini ko'rib chiqmoqchisiz?",
    "uz_cyrillic":"Қандай фоиз ставкасини кўриб чиқмоқчисиз?",
    "ru":         "По какой процентной ставке хотите рассчитать?",
}

RATE_KEYBOARD = {
    "inline_keyboard": [[
        {"text": "8% 🟢",  "callback_data": "rate|0.08"},
        {"text": "26% 🔴", "callback_data": "rate|0.26"},
    ]]
}

LOCATION_KEYWORDS = [
    # русский
    "локаци", "адрес", "где вы", "где находит", "офис", "карта", "маршрут",
    # узбекский латиница (все варианты написания)
    "manzil", "lokatsiya", "lakatsiya", "lokatsia", "qayerda", "joylashuv", "ofis",
    "xarita", "yo'nalish", "yonalish",
    # узбекский кириллица
    "манзил", "қаерда", "харита", "йўналиш",
    # английский
    "location", "address", "map",
]

SOCIAL_KEYWORDS = [
    "instagram", "инстаграм", "insta", "соцсет", "ijtimoiy",
    "социальн", "контакт", "связат",
]

SOCIAL_TEXT = {
    "uz_latin":   "📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
    "uz_cyrillic":"📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
    "ru":         "📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
}

def is_social_request(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in SOCIAL_KEYWORDS)

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

    elif cb_data.startswith("rate|"):
        rate = float(cb_data.split("|", 1)[1])
        telegram_client.answer_callback_query(cb_id)
        pending = storage.get_pending_calculation(chat_id)
        if not pending:
            return
        amount, months = pending
        storage.clear_pending_calculation(chat_id)
        current_lang = storage.get_language_lock(chat_id) or "ru"
        payment = annuity_payment(amount, rate, months)
        reply = build_payment_message(amount, months, payment, current_lang, rate=rate)
        storage.set_awaiting_contact(chat_id, amount, months)
        storage.append_message(chat_id, "assistant", reply)
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, reply)


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

    # Запрос локации — проверяем ПЕРВЫМ, до всего остального
    if is_location_request(text):
        telegram_client.send_message(chat_id, OFFICE_ADDR.get(current_lang, OFFICE_ADDR["ru"]))
        telegram_client.send_location(chat_id, OFFICE_LAT, OFFICE_LON)
        return jsonify(ok=True)

    # Запрос соцсетей / Instagram
    if is_social_request(text):
        telegram_client.send_message(chat_id, SOCIAL_TEXT.get(current_lang, SOCIAL_TEXT["ru"]))
        return jsonify(ok=True)

    # Если ранее попросили контакты — проверяем похоже ли ответ на них
    if storage.is_awaiting_contact(chat_id) and looks_like_contact_info(text):
        send_lead_to_owner(chat_id, user, text)
        storage.clear_awaiting_contact(chat_id)

    storage.append_message(chat_id, "user", text)

    # Тип кредита — запоминаем на весь диалог
    rate_from_text = guess_rate(text)
    if rate_from_text:
        storage.set_credit_rate_if_absent(chat_id, rate_from_text)

    # Если уже ждём ставку (pending_calculation задан) и клиент написал её текстом
    # вместо нажатия кнопки — считаем сразу
    if storage.is_awaiting_rate(chat_id) and rate_from_text:
        pending = storage.get_pending_calculation(chat_id)
        if pending:
            amount, months = pending
            storage.clear_pending_calculation(chat_id)
            payment = annuity_payment(amount, rate_from_text, months)
            reply = build_payment_message(amount, months, payment, current_lang, rate=rate_from_text)
            storage.set_awaiting_contact(chat_id, amount, months)
            telegram_client.send_typing(chat_id)
            storage.append_message(chat_id, "assistant", reply)
            telegram_client.send_message(chat_id, reply)
            return jsonify(ok=True)

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
        # Сохраняем сумму+срок и спрашиваем ставку кнопками
        storage.set_pending_calculation(chat_id, amount, months)
        question = RATE_QUESTION.get(current_lang, RATE_QUESTION["ru"])
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, question, reply_markup=RATE_KEYBOARD)
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
