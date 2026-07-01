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
    "ipoteka": 0.08,
    "автокредит": 0.12,
    "авто": 0.12,
    "mashina": 0.12,
    "мошина": 0.12,
    "машина": 0.12,
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


EXPLICIT_RATE_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d+)?)\s*%|"          # 8% / 26% / 12,5%
    r"по\s+(\d{1,2}(?:[.,]\d+)?)\s*процент|"  # по 8 процентов
    r"(\d{1,2}(?:[.,]\d+)?)\s*процент",     # 26 процентов
    re.IGNORECASE
)


def parse_explicit_rate(text: str) -> float | None:
    """Извлекает явно указанную процентную ставку из текста клиента.
    Например: 'по 8%', '26%', '12.5 процентов'. Только валидный диапазон 1–99%."""
    for m in EXPLICIT_RATE_RE.finditer(text):
        raw = m.group(1) or m.group(2) or m.group(3)
        if raw:
            try:
                val = float(raw.replace(",", "."))
                if 1 <= val <= 99:
                    return val / 100
            except ValueError:
                pass
    return None


def guess_rate(text: str) -> float | None:
    """Определяет ставку: сначала ищет явно указанный % в тексте,
    затем по ключевым словам типа кредита."""
    explicit = parse_explicit_rate(text)
    if explicit:
        return explicit
    low = text.lower()
    for key, rate in RATES.items():
        if key in low:
            return rate
    return None


def parse_amount(text: str) -> float | None:
    """Парсер суммы (в сумах) из текста."""
    low = text.lower().replace(" ", "")
    amount_match = re.search(r"(\d{2,}(?:[.,]\d+)?)\s*(млн|million|mln)", text.lower())
    if amount_match:
        num = float(amount_match.group(1).replace(",", "."))
        return num * 1_000_000
    plain = re.search(r"\b(\d{7,})\b", low)
    if plain:
        return float(plain.group(1))
    return None


def parse_months(text: str) -> int | None:
    """Парсер срока (в месяцах) из текста — требует явную единицу измерения
    (месяц/мес/oy/ой или год/лет/yil/йил), без неё не угадывает."""
    low = text.lower()
    months_match = re.search(r"(\d{1,3})\s*(месяц|мес|oy|ой)", low)
    if months_match:
        return int(months_match.group(1))
    years_match = re.search(r"(\d{1,2})\s*(год|лет|yil|йил)", low)
    if years_match:
        return int(years_match.group(1)) * 12
    return None


def parse_bare_years_answer(text: str) -> int | None:
    """Если клиент ответил голым числом (например просто '5') на вопрос
    'на сколько лет?' — трактуем как годы. Используется только когда
    в коде уже точно знаем, что ждём именно срок (см. app.py)."""
    stripped = text.strip()
    if re.fullmatch(r"\d{1,2}", stripped):
        years = int(stripped)
        if 1 <= years <= 30:
            return years * 12
    return None


def parse_amount_and_months(text: str):
    """Парсер суммы и срока, если оба упомянуты в ОДНОМ сообщении.
    Возвращает (amount, months) или (None, None), если не нашли оба значения.
    """
    amount = parse_amount(text)
    months = parse_months(text)

    return amount, months


def differential_payments(amount: float, annual_rate: float, months: int) -> tuple:
    """Дифференциальный расчёт: основной долг делится равными частями,
    проценты начисляются на остаток. Возвращает (first, average, last)."""
    r = annual_rate / 12
    principal = amount / months
    first   = principal + amount * r
    last    = principal + principal * r
    average = principal + amount * r * (months + 1) / (2 * months)
    return first, average, last


def annuity_payment(amount: float, annual_rate: float, months: int) -> float:
    """Псевдоним — возвращает средний платёж из дифференциальной системы."""
    _, avg, _ = differential_payments(amount, annual_rate, months)
    return avg


def format_sum(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def format_usd(amount_uzs: float, usd_rate: float) -> str:
    usd = amount_uzs / usd_rate
    return f"~${usd:,.0f}"


def build_payment_message(amount: float, months: int, payment: float, lang: str,
                          rate: float = 0.26) -> str:
    """Готовый текст про ежемесячный платёж (дифференциальный, 26%) + долларовый
    эквивалент + просьба контактов. Сформирован кодом, без участия модели."""
    try:
        from config import USD_RATE, MAX_CREDIT_AMOUNT
        usd_rate = USD_RATE
        max_amount = MAX_CREDIT_AMOUNT
    except Exception:
        usd_rate = 12800.0
        max_amount = 1_000_000_000.0

    if amount > max_amount:
        limit = format_sum(max_amount)
        usd_limit = format_usd(max_amount, usd_rate)
        over = format_sum(amount)
        if lang == "uz_latin":
            return f"Kechirasiz, maksimal kredit summasi {limit} so'm ({usd_limit}). {over} so'm bu limitdan oshib ketadi."
        if lang == "uz_cyrillic":
            return f"Кечирасиз, максимал кредит суммаси {limit} сўм ({usd_limit}). {over} сўм бу лимитдан ошиб кетади."
        return f"Извините, максимальная сумма кредита — {limit} сум ({usd_limit}). Сумма {over} сум превышает наш лимит."

    first, avg, last = differential_payments(amount, rate, months)
    rate_pct = round(rate * 100)
    a       = format_sum(amount)
    usd_amt = format_usd(amount, usd_rate)
    f_str   = format_sum(first)
    avg_str = format_sum(avg)
    l_str   = format_sum(last)
    usd_avg = format_usd(avg, usd_rate)

    if lang == "uz_latin":
        return (
            f"Ajoyib! {a} so'm ({usd_amt}) summaga {months} oy muddatga, {rate_pct}% yillik stavkada:\n\n"
            f"📊 Birinchi to'lov: {f_str} so'm\n"
            f"📊 O'rtacha to'lov: {avg_str} so'm ({usd_avg})\n"
            f"📊 Oxirgi to'lov: {l_str} so'm\n\n"
            f"Arizani tezroq ko'rib chiqilishi uchun ismingiz, familiyangiz, "
            f"qaysi tuman yoki shahardan ekanligingiz va telefon raqamingizni ayta olasizmi?"
        )
    if lang == "uz_cyrillic":
        return (
            f"Аъло! {a} сўм ({usd_amt}) суммага {months} ой муддатга, йиллик {rate_pct}% ставкада:\n\n"
            f"📊 Биринчи тўлов: {f_str} сўм\n"
            f"📊 Ўртача тўлов: {avg_str} сўм ({usd_avg})\n"
            f"📊 Охирги тўлов: {l_str} сўм\n\n"
            f"Аризани тезроқ кўриб чиқилиши учун исмингиз, фамилиянгиз, "
            f"қайси туман ёки шаҳардан эканлигингиз ва телефон рақамингизни айта оласизми?"
        )
    return (
        f"Супер! {a} сум ({usd_amt}) на {months} мес. по ставке {rate_pct}% годовых (дифференцированный расчёт):\n\n"
        f"📊 Первый платёж: {f_str} сум\n"
        f"📊 Средний платёж: {avg_str} сум ({usd_avg})\n"
        f"📊 Последний платёж: {l_str} сум\n\n"
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
