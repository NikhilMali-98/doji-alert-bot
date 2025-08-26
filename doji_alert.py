import requests

BOT_TOKEN = "6388268922:AAFc2Ki2tJ-0Nq3X6l9gCFD5tiEJKnXkWKw"
CHAT_ID = "5913646049"

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("✅ Telegram alert sent successfully")
        else:
            print(f"⚠️ Telegram error: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")

if __name__ == "__main__":
    send_telegram("🚨 Test Alert from Railway Bot ✅")
