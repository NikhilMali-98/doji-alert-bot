import time
import requests
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
    return body <= 0.2 * candle_range  # stricter doji

def check_breakout(symbol, interval):
    """Check for 2 dojis + breakout"""
    try:
        candles = client.get_klines(symbol=symbol, interval=interval, limit=5)
        # last 5 candles
        ohlc = [(float(c[1]), float(c[2]), float(c[3]), float(c[4])) for c in candles]

        # last 3 candles
        c1, c2, c3 = ohlc[-3], ohlc[-2], ohlc[-1]

        # check 2 dojis back to back
        if is_doji(*c1) and is_doji(*c2):
            doji_high = max(c1[1], c2[1])
            doji_low = min(c1[2], c2[2])

            # breakout by last candle
            if c3[3] > doji_high:  # breakout UP
                msg = f"""
🚨 Doji Breakout Alert
Coin: {symbol}
TF: {interval}
Direction: UP 🚀
Doji Range: {doji_low:.2f} - {doji_high:.2f}
Price: {c3[3]:.2f}
"""
                print(msg)
                send_telegram_message(msg)

            elif c3[3] < doji_low:  # breakout DOWN
                msg = f"""
🚨 Doji Breakout Alert
Coin: {symbol}
TF: {interval}
Direction: DOWN 🔻
Doji Range: {doji_low:.2f} - {doji_high:.2f}
Price: {c3[3]:.2f}
"""
                print(msg)
                send_telegram_message(msg)

    except Exception as e:
        print(f"⚠️ Error checking {symbol} {interval}:", e)

if __name__ == "__main__":
    print("🚀 Doji Breakout Bot Started...")
    while True:
        for sym in SYMBOLS:
            for tf in TIMEFRAMES:
                check_breakout(sym, tf)

        print("⏳ Waiting 5 minutes before next scan...")
        time.sleep(300)  # 5 minutes
