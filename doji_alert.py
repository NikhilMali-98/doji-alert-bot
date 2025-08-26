import time
import requests
from binance.client import Client
from concurrent.futures import ThreadPoolExecutor
import threading

# -------------------------------
# Telegram settings
# -------------------------------
BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"

# List of chat IDs (you + friend)
CHAT_IDS = ["1343842801"] 

# -------------------------------
# Binance settings
# -------------------------------
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "TRXUSDT", "DOTUSDT", "MATICUSDT",
    "LTCUSDT", "BCHUSDT", "AVAXUSDT", "UNIUSDT", "XLMUSDT",
    "ATOMUSDT", "XMRUSDT", "ETCUSDT", "ICPUSDT", "FILUSDT"
]

# Keep all your timeframes
TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

# -------------------------------
# Initialize Binance client
# -------------------------------
client = Client()

# -------------------------------
# Alert cache and thread lock
# -------------------------------
alerted = set()
lock = threading.Lock()

# Track last candle close times for each symbol+timeframe
last_candle_times = {}

# -------------------------------
# Functions
# -------------------------------
def send_telegram_message(message: str):
    """Send Telegram message to all chat IDs"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        payload = {"chat_id": chat_id, "text": message}
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"⚠️ Telegram error for {chat_id}:", r.text)
        except Exception as e:
            print(f"⚠️ Telegram send error for {chat_id}:", e)

def is_doji(open_, high, low, close):
    """Check if candle is strict doji"""
    body = abs(open_ - close)
    candle_range = high - low
    return body <= 0.2 * candle_range

def check_breakout(symbol, interval, alerts):
    """Check 2 dojis + breakout"""
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=5)
        ohlc = [(float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(c[6])) for c in candles]  # include close_time

        c1, c2, c3 = ohlc[-3], ohlc[-2], ohlc[-1]
        candle_close_time = c3[4]

        # Reset alerts if new candle
        key_time = (symbol, interval)
        with lock:
            if key_time not in last_candle_times or last_candle_times[key_time] != candle_close_time:
                # Remove old alerts for this symbol+interval
                alerted_copy = alerted.copy()
                for a in alerted_copy:
                    if a[0] == symbol and a[1] == interval:
                        alerted.remove(a)
                last_candle_times[key_time] = candle_close_time

        # Check doji breakout
        if is_doji(*c1[:4]) and is_doji(*c2[:4]):
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

# -------------------------------
# Main loop
# -------------------------------
if __name__ == "__main__":
    print("🚀 Doji Breakout Bot Started...")

    # Send startup test message
    send_telegram_message("🚀 Doji Breakout Bot is online and running!")

    while True:
        alerts = []

        # ThreadPool for safe multi-threading
        with ThreadPoolExecutor(max_workers=12) as executor:
            for sym in SYMBOLS:
                for tf in TIMEFRAMES:
                    executor.submit(check_breakout, sym, tf, alerts)

        # Send all alerts in batch
        if alerts:
            send_telegram_message("\n".join(alerts))
            print(f"✅ Alerts sent: {len(alerts)}")
        else:
            print("⏳ No breakout detected this cycle.")

        print("⏳ Waiting 5 minutes before next scan...")
        time.sleep(300)
