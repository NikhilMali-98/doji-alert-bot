import time
import requests
from binance.client import Client
from concurrent.futures import ThreadPoolExecutor
import threading

BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CHAT_IDS = ["1343842801"]

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'ADAUSDT', 'TRXUSDT'
]

SYMBOL_TIMEFRAMES = {
    'BTCUSDT': ["5m", "15m", "1h", "4h", "1d", "1w", "1M"],
    'ETHUSDT': ["5m", "15m", "1h", "4h", "1d", "1w", "1M"],
    'SOLUSDT': ["5m", "15m", "1h", "4h", "1d", "1w", "1M"],
}

DEFAULT_TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w", "1M"]

client = Client()
alerted = set()
lock = threading.Lock()
last_candle_times = {}

def send_telegram_message(message: str):
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
    body = abs(open_ - close)
    candle_range = high - low
    return body <= 0.2 * candle_range

def check_breakout(symbol, interval, alerts):
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=5)
        ohlc = [(float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(c[6])) for c in candles]

        c1, c2, c3 = ohlc[-3], ohlc[-2], ohlc[-1]
        candle_close_time = c3[4]

        key_time = (symbol, interval)
        with lock:
            if key_time not in last_candle_times or last_candle_times[key_time] != candle_close_time:
                alerted_copy = alerted.copy()
                for a in alerted_copy:
                    if a[0] == symbol and a[1] == interval:
                        alerted.remove(a)
                last_candle_times[key_time] = candle_close_time

        if is_doji(*c1[:4]) and is_doji(*c2[:4]):
            doji_body_high = max(c1[0], c1[3], c2[0], c2[3])
            doji_body_low = min(c1[0], c1[3], c2[0], c2[3])

            direction = None
            if c3[3] > doji_body_high:
                direction = "UP 🚀"
            elif c3[3] < doji_body_low:
                direction = "DOWN 🔻"

            if direction:
                key = (symbol, interval, direction)
                with lock:
                    if key not in alerted:
                        msg = f"""
🚨  Alert  🚨 
Coin: {symbol.replace("USDT", "USD")}
TF: {interval}
Direction: {direction}
Doji Body Range: {doji_body_low:.2f} - {doji_body_high:.2f}
Price: {c3[3]:.2f}
"""
                        alerts.append(msg)
                        alerted.add(key)

    except Exception as e:
        print(f"⚠️ Error checking {symbol} {interval}: {e}")

if __name__ == "__main__":
    print("🚀 Doji Breakout Bot Started...")
    send_telegram_message("🚀 Doji Breakout Bot is online and running!")

    while True:
        alerts = []
        with ThreadPoolExecutor(max_workers=12) as executor:
            for sym in SYMBOLS:
                tfs = SYMBOL_TIMEFRAMES.get(sym, DEFAULT_TIMEFRAMES)
                for tf in tfs:
                    executor.submit(check_breakout, sym, tf, alerts)

        if alerts:
            send_telegram_message("\n".join(alerts))
            print(f"✅ Alerts sent: {len(alerts)}")
        else:
            print("⏳ No breakout detected this cycle.")

        print("⏳ Waiting 5 minutes before next scan...")
        time.sleep(300)
