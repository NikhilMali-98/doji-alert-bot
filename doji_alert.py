import time
import requests
import threading
from binance.client import Client

# Telegram settings
BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CHAT_ID = "1343842801"

# Binance settings
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "TRXUSDT", "DOTUSDT", "MATICUSDT",
    "LTCUSDT", "BCHUSDT", "AVAXUSDT", "UNIUSDT", "XLMUSDT",
    "ATOMUSDT", "XMRUSDT", "ETCUSDT", "ICPUSDT", "FILUSDT"
]

TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

# Initialize Binance client (no API key needed for public data)
client = Client()

# Cache to prevent repeated alerts
alerted = set()
lock = threading.Lock()  # for thread-safe updates

def send_telegram_message(message: str):
    """Send Telegram notification"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print("⚠️ Telegram error:", r.text)
    except Exception as e:
        print("⚠️ Telegram send error:", e)

def is_doji(open_, high, low, close):
    """Check if candle is doji (strict)"""
    body = abs(open_ - close)
    candle_range = high - low
    return body <= 0.2 * candle_range

def check_breakout(symbol, interval, alerts):
    """Check for 2 dojis + breakout"""
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=5)
        ohlc = [(float(c[1]), float(c[2]), float(c[3]), float(c[4])) for c in candles]

        c1, c2, c3 = ohlc[-3], ohlc[-2], ohlc[-1]

        if is_doji(*c1) and is_doji(*c2):
            doji_high = max(c1[1], c2[1])
            doji_low = min(c1[2], c2[2])

            direction = None
            if c3[3] > doji_high:
                direction = "UP 🚀"
            elif c3[3] < doji_low:
                direction = "DOWN 🔻"

            if direction:
                key = (symbol, interval, direction)
                with lock:
                    if key not in alerted:
                        msg = f"""
🚨 Doji Breakout Alert
Coin: {symbol}
TF: {interval}
Direction: {direction}
Doji Range: {doji_low:.2f} - {doji_high:.2f}
Price: {c3[3]:.2f}
"""
                        alerts.append(msg)
                        alerted.add(key)

    except Exception as e:
        print(f"⚠️ Error checking {symbol} {interval}: {e}")

if __name__ == "__main__":
    print("🚀 Doji Breakout Bot Started...")

    while True:
        alerts = []
        threads = []

        for sym in SYMBOLS:
            for tf in TIMEFRAMES:
                t = threading.Thread(target=check_breakout, args=(sym, tf, alerts))
                threads.append(t)
                t.start()

        for t in threads:
            t.join()

        if alerts:
            send_telegram_message("\n".join(alerts))
            print("✅ Alerts sent:", len(alerts))
        else:
            print("⏳ No breakout detected this cycle.")

        print("⏳ Waiting 5 minutes before next scan...")
        time.sleep(300)
