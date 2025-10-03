import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from binance.client import Client
from apscheduler.schedulers.background import BackgroundScheduler
import io

# ========================
# API Keys and Config
# ========================
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01qnmrsd01kg"

CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801", "1269772473"]  # Replace with your actual Telegram chat IDs

SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))

print("🚀 Bot file loaded successfully!")

# ========================
# Telegram Helper
# ========================
def send_telegram(bot_token: str, messages: list[str], image_buf=None):
    if not messages:
        return
    payload = f"\n{SEPARATOR}\n".join(messages)
    for chat_id in CHAT_IDS:
        try:
            if image_buf:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                files = {"photo": ("chart.png", image_buf.getvalue())}
                data = {"chat_id": chat_id, "caption": payload}
                resp = requests.post(url, data=data, files=files)
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                resp = requests.post(url, json={"chat_id": chat_id, "text": payload})
            print(f"📨 Telegram send status: {resp.status_code}, response: {resp.text}")
        except Exception as e:
            print(f"{datetime.now(IST)} - Telegram error: {e}")

# ✅ Test Telegram on startup
def test_telegram():
    print("🔍 Testing Telegram connection...")
    send_telegram(CRYPTO_BOT_TOKEN, ["✅ Bot started and Telegram test message (Crypto Token)"])
    send_telegram(INDIA_BOT_TOKEN, ["✅ Bot started and Telegram test message (India Token)"])
    print("✔️ Telegram test messages sent. Check your Telegram app now.")

# ========================
# Market Scan Dummy Example (minimal debug version)
# ========================
def scan_crypto():
    print(f"{datetime.now(IST)} - DEBUG: scan_crypto() executed")
    send_telegram(CRYPTO_BOT_TOKEN, ["⚡ DEBUG: Crypto scan executed, no alerts yet"])

def scan_india():
    print(f"{datetime.now(IST)} - DEBUG: scan_india() executed")
    send_telegram(INDIA_BOT_TOKEN, ["⚡ DEBUG: India scan executed, no alerts yet"])

# ========================
# MAIN
# ========================
if __name__ == "__main__":
    print("🚀 Starting bot main...")
    test_telegram()  # <-- This will confirm Telegram works first

    scheduler = BackgroundScheduler()
    scheduler.add_job(scan_crypto, 'interval', minutes=1, id="scan_crypto")  # reduced to 1 min for testing
    scheduler.add_job(scan_india, 'interval', minutes=1, id="scan_india")
    scheduler.start()
    print("✅ Scheduler started. Scans will run every 1 minute. Watch console + Telegram.")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("🛑 Stopping bot...")
        scheduler.shutdown()
