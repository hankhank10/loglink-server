# This replaces secretstuff.py and is used to fetch environment variables

from dotenv import load_dotenv
load_dotenv()

import os

# Whatsapp credentials
whatsapp_token = os.environ.get("WHATSAPP_TOKEN")
whatsapp_phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER")
whatsapp_verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")

# Database security
app_secret_key = os.environ.get("APP_SECRET_KEY")

# Imgur credentials
imgur_client_id = os.environ.get("IMGUR_CLIENT_ID")
imgur_client_secret = os.environ.get("IMGUR_CLIENT_SECRET")

# IMGbb credentials
imgbb_api_key = os.environ.get("IMGBB_API_KEY")

# Telegram credentials
telegram_bot_name = os.environ.get("TELEGRAM_BOT_NAME")
telegram_token = os.environ.get("TELEGRAM_TOKEN")
telegram_full_token = "bot"+telegram_token
telegram_webhook_auth = os.environ.get("TELEGRAM_WEBHOOK_AUTH")

# Sentry
sentry_dsn = os.environ.get("SENTRY_DSN")

# Admin password
admin_password = os.environ.get("ADMIN_PASSWORD")

