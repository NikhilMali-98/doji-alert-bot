import time
import requests
from binance.client import Client
from concurrent.futures import ThreadPoolExecutor
import threading

# -------------------------------
# Telegram settings
# -------------------------------
BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CHAT_IDS =  ["1343842801"] 

# -------------------------------
# Binance client
# -------------------------------
client = Client()

# -------------------------------
# Settings
# -------------------------------
TIMEFRAMES = ["15m", "1h", "2h", "4h", "1d", "1w", "1M"]

# -------------------------------
# Alert cache and thread lock
# -------------------------------
alerted = set()
lock = threading.Lock()
last_candle_times = {}

# -------------------------------
# Functions
# -------------------------------
def send_telegram_message(message: str):
    """Send Telegram message to all chat IDs"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        except Exception as e:
            print("⚠️ Telegram error:", e)

def clean_symbol(symbol: str) -> str:
    """Format symbol BTCUSDT → BTCUSD"""
    return symbol[:-1] if symbol.endswith("T") else symbol

def is_doji(open_, high, low, close):
    body = abs(open_ - close)
    candle_range = high - low
    return body <= 0.2 * candle_range

def detect_patterns(ohlc):
    if len(ohlc) < 5:
        return None, None
    closes = [c[3] for c in ohlc[-5:]]
    direction, pattern = None, None

    if closes[0] > closes[1] < closes[2] > closes[3] < closes[4]:
        pattern, direction = "W", "🟢 UP 🚀"
    elif closes[0] < closes[1] > closes[2] < closes[3] > closes[4]:
        pattern, direction = "M", "🔴 DOWN 🔻"
    elif closes[0] < closes[1] > closes[2] < closes[3] > closes[4] and closes[1] > closes[3]:
        pattern, direction = "H&S", "🔴 DOWN 🔻"
    elif closes[0] > closes[1] < closes[2] > closes[3] < closes[4] and closes[1] < closes[3]:
        pattern, direction = "Inv H&S", "🟢 UP 🚀"

    return pattern, direction

def get_top_volume_symbols(limit=10):
    """Fetch top coins by 24h volume"""
    tickers = client.get_ticker()
    sorted_tickers = sorted(tickers, key=lambda x: float(x["quoteVolume"]), reverse=True)
    top_symbols = [t["symbol"] for t in sorted_tickers if t["symbol"].endswith("USDT")][:limit]
    return top_symbols

def check_patterns(symbol, interval, results):
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=10)
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

        # ---- Doji Breakout ----
        if is_doji(*c1[:4]) and is_doji(*c2[:4]):
            direction = None
            if c3[3] > max(c1[0], c1[3], c2[0], c2[3]):
                direction = "🟢 UP 🚀"
            elif c3[3] < min(c1[0], c1[3], c2[0], c2[3]):
                direction = "🔴 DOWN 🔻"

            if direction:
                key = (symbol, interval, "Doji", direction)
                with lock:
                    if key not in alerted:
                        results.append((clean_symbol(symbol), interval, "Doji Breakout", direction, c3[3]))
                        alerted.add(key)

        # ---- Chart Patterns ----
        pattern, direction = detect_patterns(ohlc)
        if pattern and direction:
            key = (symbol, interval, pattern, direction)
            with lock:
                if key not in alerted:
                    results.append((clean_symbol(symbol), interval, pattern, direction, c3[3]))
                    alerted.add(key)

    except Exception as e:
        print(f"⚠️ Error checking {symbol} {interval}: {e}")

# -------------------------------
# Main loop
# -------------------------------
if __name__ == "__main__":
    print("🚀 Doji + Patterns Bot Started...")
    send_telegram_message("🚀 Bot is online with Doji + W/M + H&S detection (Top 10 Volume Coins Only)!")

    while True:
        alerts = []
        top_symbols = get_top_volume_symbols()

        with ThreadPoolExecutor(max_workers=12) as executor:
            for sym in top_symbols:
                for tf in TIMEFRAMES:
                    executor.submit(check_patterns, sym, tf, alerts)

        if alerts:
            msg_lines = ["🚨 Pattern Alerts 🚨\n"]
            for i, (coin, tf, ptype, direction, price) in enumerate(alerts, 1):
                msg_lines.append(f"{i}) {coin} | {tf} | {ptype} | {direction} | {price:.2f}")
            send_telegram_message("\n".join(msg_lines))
            print(f"✅ Alerts sent: {len(alerts)}")
        else:
            print("⏳ No alerts this cycle.")

        print("⏳ Waiting 5 minutes before next scan...")
        time.sleep(300)
