import time
import requests
from binance.client import Client

# 🔹 Binance API (फ्री data साठी API keys लागणार नाहीत)
client = Client()

# 🔹 Telegram credentials (तुझं working token & chat_id)
BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CHAT_ID = "1343842801"

# 🔹 Alert पाठवण्यासाठी function
def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        if r.status_code != 200:
            print("⚠️ Telegram error:", r.text)
        else:
            print("✅ Telegram alert sent!")
    except Exception as e:
        print("⚠️ Telegram Exception:", e)

# 🔹 Doji check function (soft logic)
def is_doji(candle):
    open_price = float(candle[1])
    close_price = float(candle[4])
    high = float(candle[2])
    low = float(candle[3])

    body = abs(close_price - open_price)
    candle_range = high - low

    if candle_range == 0:
        return False

    # body छोटा असेल तर Doji मानायचा
    return body <= (0.2 * candle_range)

# 🔹 Breakout check
def check_breakout(symbol, tf):
    candles = client.get_klines(symbol=symbol, interval=tf, limit=5)
    last3 = candles[-3:]

    c1, c2, c3 = last3

    if is_doji(c1) and is_doji(c2):  # दोन doji back-to-back
        c2_high = float(c2[2])
        c2_low = float(c2[3])
        c3_open = float(c3[1])
        c3_close = float(c3[4])

        # Breakout वर alert
        if c3_close > c2_high:
            msg = f"""
🚨 Doji Breakout Alert 🚨
Coin: {symbol}
TF: {tf}
Direction: UP 🚀
Range: {c2_low} - {c2_high}
Price: {c3_close}
"""
            print(msg)
            send_telegram_message(msg)

        elif c3_close < c2_low:
            msg = f"""
🚨 Doji Breakout Alert 🚨
Coin: {symbol}
TF: {tf}
Direction: DOWN 🔻
Range: {c2_low} - {c2_high}
Price: {c3_close}
"""
            print(msg)
            send_telegram_message(msg)

# 🔹 Main loop
if __name__ == "__main__":
    print("🚀 Doji Breakout Bot Started...")

    SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    TIMEFRAMES = ["5m", "15m", "1h", "4h"]

    while True:
        try:
            for sym in SYMBOLS:
                for tf in TIMEFRAMES:
                    check_breakout(sym, tf)
            time.sleep(60)  # प्रत्येक 1 मिनिटाला check
        except Exception as e:
            print("⚠️ Error in loop:", e)
            time.sleep(10)
