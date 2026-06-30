"""Запустить один раз после деплоя на Railway:
   python set_webhook.py https://<ваш-домен>.up.railway.app/webhook
"""
import sys
from telegram_client import set_webhook

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python set_webhook.py https://<домен>/webhook")
        sys.exit(1)
    print(set_webhook(sys.argv[1]))
