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
