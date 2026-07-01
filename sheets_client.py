"""Google Sheets интеграция для бота Odilbek (Baraka Consulting).

Колонки таблицы:
A — Дата
B — Имя и фамилия
C — Телефон
D — Город/район
E — Сумма запроса
F — Срок (мес.)
G — Ставка (%)
H — Ежемесячный платёж (~$)
I — Язык
J — Telegram username
"""

import json
import logging
import os
import time

log = logging.getLogger("sheets_client")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID", "")
CREDS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

HEADERS = [
    "Дата", "Имя/Фамилия", "Телефон", "Город/Район",
    "Сумма (сум)", "Срок (мес.)", "Ставка (%)", "Платёж (~$)",
    "Язык", "Telegram"
]


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds_data = json.loads(CREDS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_data, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()


def ensure_headers():
    """Записывает заголовки в первую строку если она пустая."""
    if not SHEETS_ID or not CREDS_JSON:
        log.warning("[Sheets] GOOGLE_SHEETS_ID or GOOGLE_CREDENTIALS_JSON not set")
        return
    try:
        service = _get_service()
        res = service.values().get(
            spreadsheetId=SHEETS_ID, range="A1:J1"
        ).execute()
        existing = res.get("values", [])
        if not existing or not existing[0]:
            service.values().update(
                spreadsheetId=SHEETS_ID,
                range="A1:J1",
                valueInputOption="USER_ENTERED",
                body={"values": [HEADERS]}
            ).execute()
            log.info("[Sheets] Headers written")
    except Exception as e:
        log.error("[Sheets] ensure_headers failed: %s", e)


def append_lead(
    name: str,
    phone: str,
    city: str,
    amount_uzs: float | None,
    months: int | None,
    rate: float | None,
    monthly_usd: float | None,
    lang: str,
    username: str,
    date_str: str,
) -> bool:
    """Добавляет строку с данными клиента в таблицу. Возвращает True при успехе."""
    if not SHEETS_ID or not CREDS_JSON:
        log.warning("[Sheets] Not configured, skipping")
        return False
    try:
        service = _get_service()

        # Форматируем значения
        amount_str = f"{amount_uzs:,.0f}".replace(",", " ") if amount_uzs else "—"
        months_str = str(months) if months else "—"
        rate_str   = f"{round(rate * 100)}%" if rate else "—"
        usd_str    = f"~${monthly_usd:,.0f}" if monthly_usd else "—"
        lang_labels = {
            "uz_latin": "O'zbek (lotin)",
            "uz_cyrillic": "O'zbek (kirill)",
            "ru": "Русский",
        }

        row = [
            date_str,
            name or "—",
            phone or "—",
            city or "—",
            amount_str,
            months_str,
            rate_str,
            usd_str,
            lang_labels.get(lang, lang),
            username or "—",
        ]

        for attempt in range(3):
            try:
                service.values().append(
                    spreadsheetId=SHEETS_ID,
                    range="A:J",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row]}
                ).execute()
                log.info("[Sheets] Lead appended: %s %s", name, phone)
                return True
            except Exception as e:
                log.warning("[Sheets] attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return False
    except Exception as e:
        log.error("[Sheets] append_lead failed: %s", e)
        return False
