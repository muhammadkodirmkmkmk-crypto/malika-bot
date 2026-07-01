import logging
from flask import Flask, request, jsonify
from config import OWNER_CHAT_ID, OWNER_CHAT_ID_2
import storage
import telegram_client
from claude_client import ask_malika
from sheets_client import append_lead, ensure_headers
from utils import (
    guess_rate, parse_explicit_rate,
    parse_amount_and_months, parse_amount, parse_months, parse_bare_years_answer,
    annuity_payment, looks_like_contact_info, strip_markdown_asterisks,
    LANGUAGE_LOCK_LABELS, build_payment_message, format_sum,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("malika-bot")
app = Flask(__name__)

try:
    ensure_headers()
except Exception as _e:
    log.warning("ensure_headers at startup: %s", _e)

# ─── Офис ─────────────────────────────────────────────────────────────────────
OFFICE_LAT  = 41.285384
OFFICE_LON  = 69.169782
OFFICE_ADDR = {
    "uz_latin":   "📍 Toshkent, Uchtepa tumani\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📞 +998 88 478 33 33\n📸 @baraka_consulting_uz\n🕐 Du-Sha, 9:00–18:00",
    "uz_cyrillic":"📍 Тошкент, Учтепа тумани\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📞 +998 88 478 33 33\n📸 @baraka_consulting_uz\n🕐 Ду-Ша, 9:00–18:00",
    "ru":         "📍 Ташкент, Учтепинский район\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56\n📞 +998 88 478 33 33\n📸 @baraka_consulting_uz\n🕐 Пн-Сб, 9:00–18:00",
}

# ─── Выбор языка ──────────────────────────────────────────────────────────────
LANG_QUESTION = "Assalomu alaykum! 👋\n\nQaysi tilda muloqot qilishni afzal ko'rasiz?\nНа каком языке вам удобнее общаться?"
LANG_KEYBOARD = {
    "inline_keyboard": [[
        {"text": "O'zbek tili 🇺🇿", "callback_data": "lang|uz_latin"},
        {"text": "Русский язык 🇷🇺",  "callback_data": "lang|ru"},
    ]]
}

# ─── Меню услуг ───────────────────────────────────────────────────────────────
SERVICES_QUESTION = {
    "uz_latin":   "Qaysi xizmat sizni qiziqtiradi?",
    "uz_cyrillic":"Қайси хизмат сизни қизиқтиради?",
    "ru":         "Какая услуга вас интересует?",
}
SERVICES_KEYBOARD = {
    "inline_keyboard": [[
        {"text": "🏦 Kredit xizmatlari", "callback_data": "menu|credit"},
        {"text": "📋 Qo'shimcha xizmatlar", "callback_data": "menu|extra"},
    ]]
}
SERVICES_KEYBOARD_RU = {
    "inline_keyboard": [[
        {"text": "🏦 Кредитные услуги",       "callback_data": "menu|credit"},
        {"text": "📋 Дополнительные услуги",   "callback_data": "menu|extra"},
    ]]
}

CREDIT_INTRO = {
    "uz_latin":   "Assalomu alaykum! 👋 Men Odilbek — Baraka Consulting maslahatchisiman.\nKredit tanlashda yordam beraman: ipoteka, avtokredit yoki naqd pul.\nQaysi biri sizni qiziqtiradi?",
    "uz_cyrillic":"Ассалому алайкум! 👋 Мен Одилбек — Baraka Consulting маслаҳатчисиман.\nКредит танлашда ёрдам бераман: ипотека, автокредит ёки нақд пул.\nҚайси бири сизни қизиқтиради?",
    "ru":         "Здравствуйте! 👋 Я Одилбек, консультант Baraka Consulting.\nПомогу подобрать кредит — ипотека, авто или наличные.\nЧто вас интересует?",
}

EXTRA_SERVICES = {
    "uz_latin": (
        "📋 Qo'shimcha xizmatlarimiz:\n\n"
        "🔵 Pechat yasash — yuridik va jismoniy shaxslar uchun\n"
        "🔵 Propiskaga qo'yish — doimiy va vaqtincha ro'yxatga qo'yish\n"
        "🔵 Kadastr yangilash — ariza topshirish va hujjatlarni rasmiylashtirish\n"
        "🔵 Yuridik maslahat — barcha huquqiy masalalar bo'yicha\n"
        "🔵 Firma ochish / yopish — ariza topshirish va rasmiylashtirish\n"
        "🔵 Buxgalteriya xizmati — hisobotlar, soliqlar va maslahat\n\n"
        "📞 Bog'lanish:\n+998 95 087 77 66\n+998 99 939 55 56\n+998 88 478 33 33\n"
        "📸 @baraka_consulting_uz\n🕐 Du-Sha, 9:00–18:00"
    ),
    "uz_cyrillic": (
        "📋 Қўшимча хизматларимиз:\n\n"
        "🔵 Печат ясаш — юридик ва жисмоний шахслар учун\n"
        "🔵 Пропискага қўйиш — доимий ва вақтинча рўйхатга қўйиш\n"
        "🔵 Кадастр янгилаш — ариза ва ҳужжатларни расмийлаштириш\n"
        "🔵 Юридик маслаҳат — барча ҳуқуқий масалалар бўйича\n"
        "🔵 Firma ochish / yopish — ариза ва расмийлаштириш\n"
        "🔵 Бухгалтерия хизмати — ҳисоботлар, солиқлар ва маслаҳат\n\n"
        "📞 Боғланиш:\n+998 95 087 77 66\n+998 99 939 55 56\n+998 88 478 33 33\n"
        "📸 @baraka_consulting_uz\n🕐 Ду-Ша, 9:00–18:00"
    ),
    "ru": (
        "📋 Дополнительные услуги:\n\n"
        "🔵 Изготовление печатей — для юр. и физ. лиц\n"
        "🔵 Прописка — постоянная и временная регистрация\n"
        "🔵 Обновление кадастра — подача заявки и оформление документов\n"
        "🔵 Юридическая консультация — по всем правовым вопросам\n"
        "🔵 Открытие / закрытие фирмы — заявка и оформление\n"
        "🔵 Бухгалтерские услуги — учёт, налоги, отчёты и консультации\n\n"
        "📞 Связаться с нами:\n+998 95 087 77 66\n+998 99 939 55 56\n+998 88 478 33 33\n"
        "📸 @baraka_consulting_uz\n🕐 Пн-Сб, 9:00–18:00"
    ),
}

# ─── Вопрос ставки ────────────────────────────────────────────────────────────
TERM_QUESTION = {
    "uz_latin":   "Yaxshi! Qancha muddatga olmoqchisiz? (5 yildan 10 yilgacha)",
    "uz_cyrillic":"Яхши! Қанча муддатга олмоқчисиз? (5 йилдан 10 йилгача)",
    "ru":         "Отлично! На какой срок рассматриваете? (от 5 до 10 лет)",
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

# ─── Ключевые слова ───────────────────────────────────────────────────────────
LOCATION_KEYWORDS = [
    "локаци","адрес","где вы","где находит","офис","карта","маршрут",
    "manzil","lokatsiya","lakatsiya","lokatsia","qayerda","joylashuv","ofis",
    "xarita","yo'nalish","yonalish","манзил","қаерда","харита","location","address","map",
]
SOCIAL_KEYWORDS = [
    "instagram","инстаграм","insta","соцсет","ijtimoiy","социальн","контакт","связат",
]
SOCIAL_TEXT = {
    "uz_latin":   "📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
    "uz_cyrillic":"📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
    "ru":         "📸 Instagram: @baraka_consulting_uz\nhttps://www.instagram.com/baraka_consulting_uz\n\n📞 +998 95 087 77 66\n📞 +998 99 939 55 56",
}

def is_location_request(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in LOCATION_KEYWORDS)

def is_social_request(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in SOCIAL_KEYWORDS)

# ─── Уведомления ──────────────────────────────────────────────────────────────
def parse_contact_text(text: str) -> tuple:
    import re
    phone_re = re.compile(r"(\+?998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b\d{9}\b)")
    phone_match = phone_re.search(text)
    phone = phone_match.group(0) if phone_match else ""
    without_phone = phone_re.sub("", text).strip()
    parts = [p.strip(" ,;") for p in without_phone.replace("\n", ",").split(",") if p.strip()]
    name = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    return name, phone, city

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

    from datetime import datetime
    import pytz
    TZ = pytz.timezone("Asia/Tashkent")
    date_str = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    name, phone, city = parse_contact_text(contact_text)
    amount = amount_months[0] if amount_months else None
    months = amount_months[1] if amount_months else None
    rate = storage.get_credit_rate(chat_id)
    lang = storage.get_language_lock(chat_id) or "ru"
    monthly_usd = None
    if amount and months and rate:
        from utils import differential_payments
        from config import USD_RATE
        _, avg, _ = differential_payments(amount, rate, months)
        monthly_usd = avg / USD_RATE
    append_lead(
        name=name, phone=phone, city=city,
        amount_uzs=amount, months=months, rate=rate,
        monthly_usd=monthly_usd, lang=lang,
        username=username, date_str=date_str,
    )

# ─── Callback ─────────────────────────────────────────────────────────────────
def handle_callback(data: dict) -> None:
    cb_data = data.get("data", "")
    chat_id = data["message"]["chat"]["id"]
    cb_id   = data["id"]

    if cb_data.startswith("lang|"):
        lang = cb_data.split("|", 1)[1]
        storage.set_language_lock(chat_id, lang)
        telegram_client.answer_callback_query(cb_id)
        question = SERVICES_QUESTION.get(lang, SERVICES_QUESTION["ru"])
        keyboard = SERVICES_KEYBOARD_RU if lang == "ru" else SERVICES_KEYBOARD
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, question, reply_markup=keyboard)

    elif cb_data.startswith("menu|"):
        service = cb_data.split("|", 1)[1]
        telegram_client.answer_callback_query(cb_id)
        lang = storage.get_language_lock(chat_id) or "ru"
        telegram_client.send_typing(chat_id)
        if service == "credit":
            reply = CREDIT_INTRO.get(lang, CREDIT_INTRO["ru"])
            storage.append_message(chat_id, "assistant", reply)
            telegram_client.send_message(chat_id, reply)
        elif service == "extra":
            reply = EXTRA_SERVICES.get(lang, EXTRA_SERVICES["ru"])
            telegram_client.send_message(chat_id, reply)
            telegram_client.send_location(chat_id, OFFICE_LAT, OFFICE_LON)

    elif cb_data.startswith("rate|"):
        rate = float(cb_data.split("|", 1)[1])
        telegram_client.answer_callback_query(cb_id)
        pending = storage.get_pending_calculation(chat_id)
        if not pending:
            return
        amount, months = pending
        storage.clear_pending_calculation(chat_id)
        storage.set_credit_rate(chat_id, rate)
        current_lang = storage.get_language_lock(chat_id) or "ru"
        payment = annuity_payment(amount, rate, months)
        reply = build_payment_message(amount, months, payment, current_lang, rate=rate)
        storage.set_awaiting_contact(chat_id, amount, months)
        storage.append_message(chat_id, "assistant", reply)
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, reply)

# ─── Webhook ──────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}

    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return jsonify(ok=True)

    message = update.get("message")
    if not message or "text" not in message:
        return jsonify(ok=True)

    chat_id = message["chat"]["id"]
    user    = message.get("from", {})
    text    = message["text"]

    if text.strip() == "/start":
        storage._language_lock.pop(chat_id, None)
        telegram_client.send_message(chat_id, LANG_QUESTION, reply_markup=LANG_KEYBOARD)
        return jsonify(ok=True)

    if not storage.is_language_chosen(chat_id):
        telegram_client.send_message(chat_id, LANG_QUESTION, reply_markup=LANG_KEYBOARD)
        return jsonify(ok=True)

    current_lang = storage.get_language_lock(chat_id)

    # Локация — первым, до всего остального
    if is_location_request(text):
        telegram_client.send_message(chat_id, OFFICE_ADDR.get(current_lang, OFFICE_ADDR["ru"]))
        telegram_client.send_location(chat_id, OFFICE_LAT, OFFICE_LON)
        return jsonify(ok=True)

    if is_social_request(text):
        telegram_client.send_message(chat_id, SOCIAL_TEXT.get(current_lang, SOCIAL_TEXT["ru"]))
        return jsonify(ok=True)

    # Контакты клиента
    if storage.is_awaiting_contact(chat_id) and looks_like_contact_info(text):
        send_lead_to_owner(chat_id, user, text)
        storage.clear_awaiting_contact(chat_id)

    storage.append_message(chat_id, "user", text)

    # Тип кредита
    rate_from_text = guess_rate(text)
    if rate_from_text:
        storage.set_credit_rate_if_absent(chat_id, rate_from_text)

    # Если ждём ставку и клиент написал её текстом
    if storage.is_awaiting_rate(chat_id) and rate_from_text:
        pending = storage.get_pending_calculation(chat_id)
        if pending:
            amount, months = pending
            storage.clear_pending_calculation(chat_id)
            storage.set_credit_rate(chat_id, rate_from_text)
            payment = annuity_payment(amount, rate_from_text, months)
            reply = build_payment_message(amount, months, payment, current_lang, rate=rate_from_text)
            storage.set_awaiting_contact(chat_id, amount, months)
            telegram_client.send_typing(chat_id)
            storage.append_message(chat_id, "assistant", reply)
            telegram_client.send_message(chat_id, reply)
            return jsonify(ok=True)

    # Парсинг суммы и срока
    amount, months = parse_amount_and_months(text)
    rate = rate_from_text if (amount and months) else None
    if not (amount and months):
        amt_only    = parse_amount(text)
        months_only = parse_months(text)
        pending     = storage.get_pending_amount(chat_id)
        if amt_only and not months_only:
            storage.set_pending_amount(chat_id, amt_only, rate_from_text)
            # Спрашиваем срок сами — не передаём Claude
            question = TERM_QUESTION.get(current_lang, TERM_QUESTION["ru"])
            telegram_client.send_typing(chat_id)
            telegram_client.send_message(chat_id, question)
            return jsonify(ok=True)
        elif pending and (months_only or parse_bare_years_answer(text)):
            amount, rate = pending
            months = months_only or parse_bare_years_answer(text)
            storage.clear_pending_amount(chat_id)

    if amount and months:
        storage.set_pending_calculation(chat_id, amount, months)
        question = RATE_QUESTION.get(current_lang, RATE_QUESTION["ru"])
        telegram_client.send_typing(chat_id)
        telegram_client.send_message(chat_id, question, reply_markup=RATE_KEYBOARD)
        return jsonify(ok=True)

    # Claude
    telegram_client.send_typing(chat_id)
    dynamic_addendum = (
        f"Язык этого диалога ЗАФИКСИРОВАН: {LANGUAGE_LOCK_LABELS[current_lang]}. "
        f"Отвечай ТОЛЬКО на этом языке. Твоё имя — Odilbek, не Malika."
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
