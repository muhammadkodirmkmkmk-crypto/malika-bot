import re

PHONE_RE = re.compile(r"(\+?998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b\d{9}\b)")

HOT_KEYWORDS_RU = [
    "готов оформить", "хочу оформить", "когда можно прийти", "запишите меня",
    "оформляем", "готова оформить", "приду сегодня", "приду завтра", "звоните мне",
]
HOT_KEYWORDS_UZ = [
    "rasmiylashtir", "kelaman", "qachon kela olaman", "tayyorman", "yozib qo'ying",
    "qo'ng'iroq qiling",
]

RATES = {
    "ипотека": 0.08,
    "ипотечный": 0.08,
    "жиль": 0.08,
    "uy": 0.08,
    "автокредит": 0.12,
    "авто": 0.12,
    "mashina": 0.12,
    "avtokredit": 0.12,
    "наличны": 0.15,
    "naqd": 0.15,
}

AMOUNT_RE = re.compile(r"(\d[\d\s.,]{4,})\s*(млн|миллион|mln)?")
MONTHS_RE = re.compile(r"(\d{1,3})\s*(месяц|мес|oy|yil|год|лет)")


def detect_uzbek(text: str) -> bool:
    """Грубая эвристика: характерные узбекские буквы/слова."""
    uzbek_markers = ["o'", "g'", "ў", "қ", "ҳ", "uchun", "bo'l", "qil", "kerak", "iltimos"]
    low = text.lower()
    return any(m in low for m in uzbek_markers)


UZBEK_CYRILLIC_ONLY_RE = re.compile(r"[ўқғҳ]", re.IGNORECASE)
UZBEK_CYRILLIC_WORDS = [
    "керак", "илтимос", "хохлайман", "хоҳлайман", "беринг", "айтинг",
    "яхши", "раҳмат", "рахмат", "мумкин", "бўлади", "буладими", "qancha",
    "канча", "учун", "менга", "сизга", "олмоқчиман", "оламан",
]


RUSSIAN_MARKERS = [
    "здравствуйте", "привет", "хочу", "нужен", "нужно", "можно", "пожалуйста",
    "спасибо", "сколько", "какой", "какая", "какие", "это", "вы", "меня",
]


def detect_language_lock(text: str) -> str | None:
    """Определяет язык+алфавит по сообщению клиента для фиксации на весь диалог.
    Возвращает 'uz_cyrillic' | 'uz_latin' | 'ru' | None (если непонятно).
    Алфавит важнее точного языка: если в тексте кириллица — отвечаем
    кириллицей (рус. или узб.-кириллица), если латиница — латиницей,
    чтобы визуально скрипт ответа никогда не расходился со скриптом клиента."""
    low = text.lower()
    has_uz_latin_marker = any(m in low for m in ["o'", "g'", "ʻ", "uchun", "bo'l", "qil", "kerak"])
    has_uz_cyrillic_marker = bool(UZBEK_CYRILLIC_ONLY_RE.search(text)) or any(
        w in low for w in UZBEK_CYRILLIC_WORDS
    )
    if has_uz_cyrillic_marker:
        return "uz_cyrillic"
    if has_uz_latin_marker:
        return "uz_latin"
    if re.search(r"[а-яё]", low):
        # кириллица без явных узбекских маркеров — чаще всего русский,
        # но в любом случае отвечаем кириллицей, а не латиницей
        return "ru"
    if re.search(r"[a-z]", low):
        # латиница без явных маркеров — по умолчанию узбекская латиница
        # (компания работает с узбекскими клиентами)
        if any(m in low for m in RUSSIAN_MARKERS):
            return "ru"
        return "uz_latin"
    return None


LANGUAGE_LOCK_LABELS = {
    "uz_cyrillic": "узбекский, алфавит КИРИЛЛИЦА (не переключайся на латиницу)",
    "uz_latin": "узбекский, алфавит ЛОТИН/латиница (не переключайся на кириллицу)",
    "ru": "русский",
}


def detect_hot_lead(text: str) -> bool:
    low = text.lower()
    if PHONE_RE.search(text):
        return True
    if any(k in low for k in HOT_KEYWORDS_RU):
        return True
    if any(k in low for k in HOT_KEYWORDS_UZ):
        return True
    return False


def extract_phone(text: str) -> str | None:
    m = PHONE_RE.search(text)
    return m.group(0) if m else None


def guess_rate(text: str) -> float | None:
    low = text.lower()
    for key, rate in RATES.items():
        if key in low:
            return rate
    return None


def parse_amount_and_months(text: str):
    """Очень грубый парсер суммы (в сумах) и срока (в месяцах) из текста.
    Возвращает (amount, months) или (None, None), если не нашли оба значения.
    """
    low = text.lower().replace(" ", "")

    amount = None
    amount_match = re.search(r"(\d{2,}(?:[.,]\d+)?)\s*(млн|million|mln)", text.lower())
    if amount_match:
        num = float(amount_match.group(1).replace(",", "."))
        amount = num * 1_000_000
    else:
        plain = re.search(r"\b(\d{7,})\b", low)
        if plain:
            amount = float(plain.group(1))

    months = None
    months_match = re.search(r"(\d{1,3})\s*(месяц|мес|oy)", text.lower())
    if months_match:
        months = int(months_match.group(1))
    else:
        years_match = re.search(r"(\d{1,2})\s*(год|лет|yil)", text.lower())
        if years_match:
            months = int(years_match.group(1)) * 12

    return amount, months


def annuity_payment(amount: float, annual_rate: float, months: int) -> float:
    """Аннуитетный платёж: P*r*(1+r)^n / ((1+r)^n - 1)."""
    r = annual_rate / 12
    if r == 0:
        return amount / months
    factor = (1 + r) ** months
    return amount * r * factor / (factor - 1)


def format_sum(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def build_payment_message(amount: float, months: int, payment: float, lang: str) -> str:
    """Готовый текст про ежемесячный платёж + просьба контактов,
    полностью сформированный кодом (без участия модели) на нужном языке."""
    a, m, p = format_sum(amount), months, format_sum(payment)
    if lang == "uz_latin":
        return (
            f"Ajoyib! {a} so'm summaga {m} oy muddatga oylik to'lov taxminan {p} so'm bo'ladi 😊\n\n"
            f"Arizani tezroq ko'rib chiqilishi uchun ismingiz, familiyangiz, qaysi tuman "
            f"yoki shahardan ekanligingiz va telefon raqamingizni ayta olasizmi?"
        )
    if lang == "uz_cyrillic":
        return (
            f"Аъло! {a} сўм суммага {m} ой муддатга ойлик тўлов тахминан {p} сўм бўлади 😊\n\n"
            f"Аризани тезроқ кўриб чиқилиши учун исмингиз, фамилиянгиз, қайси туман "
            f"ёки шаҳардан эканлигингиз ва телефон рақамингизни айта оласизми?"
        )
    return (
        f"Супер! По {a} сум на {m} мес. ежемесячный платёж составит примерно {p} сум 😊\n\n"
        f"Чтобы заявку рассмотрели быстрее, подскажите, пожалуйста, ваше имя, фамилию, "
        f"город/район проживания и номер телефона?"
    )


def looks_like_contact_info(text: str) -> bool:
    """Грубая проверка: похоже ли сообщение на 'Имя Фамилия, город, телефон',
    а не на отдельное слово/смайлик. Достаточно телефона ИЛИ пары слов."""
    if extract_phone(text):
        return True
    cleaned = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).strip()
    words = [w for w in cleaned.split() if len(w) > 1]
    if len(words) < 2:
        return False
    alpha_words = [w for w in words if any(ch.isalpha() for ch in w)]
    return len(alpha_words) >= 2


SYSTEM_NOTE_LEAK_RE = re.compile(r"\[SYSTEM NOTE\][^\n]*\n?", re.IGNORECASE)


def strip_system_note_leak(text: str) -> str:
    """Страховка: если модель случайно процитировала служебную подсказку,
    вырезаем эту строку перед отправкой клиенту."""
    return SYSTEM_NOTE_LEAK_RE.sub("", text).strip()


def strip_markdown_asterisks(text: str) -> str:
    """Страховка: убирает **bold**/*italic* разметку, которую Telegram
    не рендерит без parse_mode — иначе клиент видит звёздочки как есть."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    return text
