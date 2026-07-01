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
    r"(\d{1,2}(?:[.,]\d+)?)\s*%|"
    r"по\s+(\d{1,2}(?:[.,]\d+)?)\s*процент|"
    r"(\d{1,2}(?:[.,]\d+)?)\s*процент|"
    r"(\d{1,2}(?:[.,]\d+)?)\s*(?:фоизлик|фоиз|foizlik|foiz)",
    re.IGNORECASE
)


def parse_explicit_rate(text: str) -> float | None:
    """Извлекает явно указанную процентную ставку из текста клиента."""
    for m in EXPLICIT_RATE_RE.finditer(text):
        raw = m.group(1) or m.group(2) or m.group(3) or m.group(4)
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
    """Парсер суммы (в сумах) из текста. Поддерживает млн/mln, доллары, минг/ming."""
    low = text.lower()

    # Миллионы сумов: 500 млн, 50mln, 300 million
    amount_match = re.search(r"(\d{2,}(?:[.,]\d+)?)\s*(млн|million|mln)", low)
    if amount_match:
        num = float(amount_match.group(1).replace(",", "."))
        return num * 1_000_000

    # Тысячи: 20 минг, 20 ming, 20 тысяч, 20k
    thousand_match = re.search(
        r"(\d{1,6}(?:[.,]\d+)?)\s*(?:минг|ming|тысяч|тыс|k\b)",
        low
    )
    if thousand_match:
        num = float(thousand_match.group(1).replace(",", "."))
        amount_in_units = num * 1000
        # Если число тысяч похоже на долларовую сумму (до ~100 000$) — конвертируем в сумы
        if amount_in_units <= 100_000:
            try:
                from config import USD_RATE
                return amount_in_units * USD_RATE
            except ImportError:
                return amount_in_units * 12800
        return amount_in_units

    # Доллары: 20000$, $20000, 20000 dollar, 20000 usd
    dollar_match = re.search(
        r"\$\s*([\d\s.,]+)|([\d\s.,]+)\s*(?:\$|dollar|usd|дол)",
        low
    )
    if dollar_match:
        raw = (dollar_match.group(1) or dollar_match.group(2) or "").replace(" ", "").replace(",", "")
        try:
            usd_val = float(raw)
            if usd_val >= 100:
                from config import USD_RATE
                return usd_val * USD_RATE
        except (ValueError, ImportError):
            pass

    # Голое большое число (от 7 цифр = минимум 1 млн сум)
    plain = re.search(r"\b(\d{7,})\b", low.replace(" ", ""))
    if plain:
        return float(plain.group(1))
    return None


def parse_months(text: str) -> int | None:
    """Парсер срока (в месяцах) из текста."""
    low = text.lower()
    months_match = re.search(r"(\d{1,3})\s*(месяц|мес|oy|ой)", low)
    if months_match:
        return int(months_match.group(1))
    # yilga, yilda, yildan — узбекский с падежными суффиксами
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
    """Простое сообщение: одна цифра среднего платежа в $ и сумах."""
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
        if lang == "uz_latin":
            return f"Kechirasiz, maksimal kredit summasi {limit} so'm ({usd_limit})."
        if lang == "uz_cyrillic":
            return f"Кечирасиз, максимал кредит суммаси {limit} сўм ({usd_limit})."
        return f"Извините, максимальная сумма кредита — {limit} сум ({usd_limit})."

    _, avg, _ = differential_payments(amount, rate, months)
    rate_pct   = round(rate * 100)
    years      = months // 12
    usd_amt    = format_usd(amount, usd_rate)
    avg_sum    = format_sum(avg)
    avg_usd    = format_usd(avg, usd_rate)

    if lang == "uz_latin":
        return (
            f"✅ {usd_amt} summaga {years} yil, {rate_pct}% stavkada —\n"
            f"oyiga taxminan {avg_usd} ({avg_sum} so'm) to'laysiz.\n\n"
            f"Arizani tezroq ko'rib chiqilishi uchun ismingiz, familiyangiz, "
            f"qaysi tuman yoki shahardan ekanligingiz va telefon raqamingizni ayta olasizmi?"
        )
    if lang == "uz_cyrillic":
        return (
            f"✅ {usd_amt} суммага {years} йил, {rate_pct}% ставкада —\n"
            f"ойига тахминан {avg_usd} ({avg_sum} сўм) тўлайсиз.\n\n"
            f"Аризани тезроқ кўриб чиқилиши учун исмингиз, фамилиянгиз, "
            f"қайси туман ёки шаҳардан эканлигингиз ва телефон рақамингизни айта оласизми?"
        )
    return (
        f"✅ {usd_amt} на {years} лет, {rate_pct}% годовых —\n"
        f"ежемесячно примерно {avg_usd} ({avg_sum} сум).\n\n"
        f"Чтобы заявку рассмотрели быстрее, подскажите ваше имя, фамилию, "
        f"город/район и номер телефона?"
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
