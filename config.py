import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Кому пересылать "горячих" лидов (телефон/имя/готовность оформлять)
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

# Модель Claude для генерации ответов Малики
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# Сколько последних сообщений диалога хранить как контекст
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
