import time
import pandas as pd
from binance.client import Client
import requests

# 🔑 तुझे Telegram Keys
BOT_TOKEN = "6388268922:AAFc2Ki2tJ-0Nq3X6l9gCFD5tiEJKnXkWKw"
CHAT_ID = "5913646049"

# Binance client (API key लागणार नाही फक्त public data घेण्यासाठी)
client = Client()

# Function: Telegram ला मेसेज पाठवण्यासाठी
def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram Error:", e)

# Doji ओळखण्यासाठी (थोडा soft logic ठेवला आहे)
def is_doji(candle):
    body = abs(float(candle['close']) - float(candle['open']))
    candle_range = float(candle['high']) - float(candle['low'])
    if candle_range == 0:
        return False
    return (body / candle_range) < 0.3   # 30% पर्यंत चालेल

# Main logic
def check_for_doji_breakout(symbol="BTCUSDT", interval="1h", limit=10):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'time','open','high','low','close','volume',
        'c_close','c_volume','ignore','taker_buy_base','taker_buy_quote','ignore2'
    ])

    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    # शेवटच्या 3 candles: [ -3 , -2 , -1 ]
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]

    if is_doji(c1) and is_doji(c2):
        doji_high = max(c1['high'], c2['high'])
        doji_low = min(c1['low'], c2['low'])

        breakout = None
        if c3['close'] > doji_high:
            breakout = "UP 🔼"
        elif c3['close'] < doji_low:
            breakout = "DOWN 🔻"

        if breakout:
            msg = (
                f"🚨 Doji Breakout Alert\n"
                f"Symbol: {symbol}\n"
                f"Timeframe: {interval}\n"
                f"Direction: {breakout}\n"
                f"Doji Range: {doji_low:.2f} - {doji_high:.2f}\n"
                f"Price: {c3['close']:.2f}"
            )
            print(msg)  # console log
            send_telegram_message(msg)

# Loop
if __name__ == "__main__":
    send_telegram_message("✅ Doji Breakout Bot Started")
    while True:
        try:
            check_for_doji_breakout("BTCUSDT", "1h")
            time.sleep(60)  # दर 1 मिनिटाने check करेल
        except Exception as e:
            print("Error:", e)
            time.sleep(10)
