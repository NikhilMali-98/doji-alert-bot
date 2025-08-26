
import time
import pandas as pd
from binance.client import Client
import requests

# =====================
# Telegram Config (तुझं actual key/chat id मी आधीपासून माहित आहे म्हणून direct टाकलं आहे)
# =====================
BOT_TOKEN = "6388268922:AAFc2Ki2tJ-0Nq3X6l9gCFD5tiEJKnXkWKw"
CHAT_ID = "5913646049"

# =====================
# Binance Client (No API key needed for public data)
# =====================
client = Client()

# =====================
# Functions
# =====================
def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram Error:", e)

def get_klines(symbol, interval="15m", limit=10):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qav","num_trades","taker_base","taker_quote","ignore"
        ])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print("Error fetching data:", e)
        return None

def is_doji(candle):
    body = abs(candle["close"] - candle["open"])
    rng = candle["high"] - candle["low"]
    return body <= 0.25 * rng  # body <= 25% range → doji

def check_for_breakout(symbol, interval="15m"):
    df = get_klines(symbol, interval, 10)
    if df is None or len(df) < 3:
        return

    # शेवटच्या ३ candles
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]

    if is_doji(c1) and is_doji(c2):
        doji_high = max(c1["high"], c2["high"])
        doji_low = min(c1["low"], c2["low"])

        if c3["close"] > doji_high:
            direction = "UP 🚀"
        elif c3["close"] < doji_low:
            direction = "DOWN 🔻"
        else:
            return  # No breakout

        msg = f"🚨 Doji Breakout Alert\nCoin: {symbol}\nTF: {interval}\nDirection: {direction}\nRange: {doji_low} - {doji_high}\nPrice: {c3['close']}"
        print(msg)
        send_telegram_message(msg)

# =====================
# Main Loop
# =====================
if __name__ == "__main__":
    print("✅ Doji Breakout Bot Started...")
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "BCHUSDT"]

    while True:
        for sym in symbols:
            for tf in ["15m", "1h", "4h"]:
                check_for_breakout(sym, tf)
        time.sleep(60)  # प्रत्येक १ मिनिटाला check
