import requests
import time
import threading
from binance.client import Client
from collections import deque


API_KEY = ""
API_SECRET = ""
client = Client(API_KEY, API_SECRET)

# Telegram
BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CHAT_IDS = ["1343842801"]  # add multiple chat IDs here

# Timeframes
TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

# Store already alerted signals
alerted = set()
lock = threading.Lock()

def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, data=payload)
        except Exception as e:
            print("Telegram Error:", e)

# Doji check (body very small)
def is_doji(o, h, l, c, threshold=0.1):
    body = abs(c - o)
    rng = h - l if h - l != 0 else 1
    return (body / rng) <= threshold

def check_breakout(symbol, interval):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=5)
        if len(klines) < 3:
            return None

        # Take last 3 candles
        c1, c2, c3 = klines[-3], klines[-2], klines[-1]

        o1, h1, l1, c1c = float(c1[1]), float(c1[2]), float(c1[3]), float(c1[4])
        o2, h2, l2, c2c = float(c2[1]), float(c2[2]), float(c2[3]), float(c2[4])
        o3, h3, l3, c3c = float(c3[1]), float(c3[2]), float(c3[3]), float(c3[4])

        # check if 2 dojis formed
        if is_doji(o1, h1, l1, c1c) and is_doji(o2, h2, l2, c2c):
            # Doji body range
            doji_high = max(o1, c1c, o2, c2c)
            doji_low = min(o1, c1c, o2, c2c)

            direction = None
            # check breakout when current candle tries to break doji body
            if o3 > doji_high or c3c > doji_high:
                direction = "UP 🚀"
            elif o3 < doji_low or c3c < doji_low:
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
Doji Body Range: {doji_low:.2f} - {doji_high:.2f}
Price: {c3c:.2f}
"""
                        send_telegram_message(msg)
                        alerted.add(key)

    except Exception as e:
        print(f"Error in {symbol}-{interval}:", e)

def worker(symbol):
    while True:
        for tf in TIMEFRAMES:
            check_breakout(symbol, tf)
        time.sleep(5 * 60)  # run every 5 minutes

def run_bot(symbols):
    threads = []
    for sym in symbols:
        t = threading.Thread(target=worker, args=(sym,))
        t.start()
        threads.append(t)

if __name__ == "__main__":
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT",
               "XRPUSDT", "ADAUSDT", "SOLUSDT", 
               "DOGEUSDT", "TRXUSDT", "DOTUSDT", 
               "MATICUSDT", "LTCUSDT", "BCHUSDT", 
               "AVAXUSDT", "UNIUSDT", "XLMUSDT", 
               "ATOMUSDT", "XMRUSDT", "ETCUSDT",
               "ICPUSDT", "FILUSDT"]  # add more pairs
    run_bot(SYMBOLS)
   
