import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from binance.client import Client
from apscheduler.schedulers.background import BackgroundScheduler
import io

# API Keys
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01qnmrsd01kg"

# Bot Configuration
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801", "1269772473"]
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BIG_TFS = {"4h", "1d", "1w", "1M"}
TF_COOLDOWN_SEC = {
    "5m": 240,
    "15m": 720,
    "30m": 1500,
    "1h": 3300,
    "2h": 6600,
    "4h": 13200,
    "1d": 79200,
    "1w": 561600,
    "1M": 2505600
}
CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
CRYPTO_TFS = ["15m", "1h", "2h", "4h", "1d", "1w", "1M"]
INDICES_MAP = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"]
}
TOP15_STOCKS_NS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "LT.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","HINDUNILVR.NS","ASIANPAINTS.NS","MARUTI.NS","BAJFINANCE.NS"
]

# ✅ Updated TFs for Yahoo Finance
INDEX_TFS = ["15m", "1h", "4h", "1d", "1wk", "1mo"]
STOCK_TFS = ["15m", "1h", "4h", "1d", "1wk", "1mo"]

BINANCE_INTERVALS = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M"
}

# Initialize Binance Client
BINANCE = Client()

# State tracking
last_alert_at = {}
last_bar_key = set()
alpha_cache = {"last_time": 0, "data": {}}
finnhub_cache = {"last_time": 0, "data": {}}
API_RATE_LIMITS = {
    "ALPHA_VANTAGE": {"max_calls": 5, "window_seconds": 60, "calls": 0, "last_reset": 0},
    "FINNHUB": {"max_calls": 60, "window_seconds": 60, "calls": 0, "last_reset": 0}
}

def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def is_india_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

# ✅ Updated mapping to YF-supported intervals
def tf_to_pandas(tf: str) -> str:
    mapping = {
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "60m",
        "2h": "60m",  # fallback
        "4h": "4h",
        "1d": "1d",
        "1w": "1wk",
        "1M": "1mo"
    }
    return mapping.get(tf, tf)

def cooldown_ok(market: str, symbol: str, tf: str, direction: str) -> bool:
    key = (market, symbol, tf, direction)
    now = int(datetime.now(IST).timestamp())
    cd = TF_COOLDOWN_SEC.get(tf, 600)
    last = last_alert_at.get(key, 0)
    if now - last >= cd:
        last_alert_at[key] = now
        return True
    return False

def check_api_limit(api_name: str) -> bool:
    limit = API_RATE_LIMITS[api_name]
    now = time.time()
    if now - limit["last_reset"] > limit["window_seconds"]:
        limit["last_reset"] = now
        limit["calls"] = 0
    if limit["calls"] < limit["max_calls"]:
        limit["calls"] += 1
        return True
    print(f"{ist_now_str()} - API limit exceeded for {api_name}")
    return False

def send_telegram(bot_token: str, messages: list[str], image_buf=None):
    if not messages:
        return
    payload = f"\n{SEPARATOR}\n".join(messages)
    for chat_id in CHAT_IDS:
        try:
            if image_buf:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                files = {"photo": ("chart.png", image_buf.getvalue())}
                data = {"chat_id": chat_id, "caption": payload}
                requests.post(url, data=data, files=files)
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={"chat_id": chat_id, "text": payload})
        except Exception as e:
            print(f"{ist_now_str()} - Telegram error: {e}")

def is_doji(open_, high, low, close, volume=None):
    body = abs(open_ - close)
    rng = high - low
    if rng == 0:
        return True, True
    if body <= 0.02 * rng or body <= 0.00003 * close:
        if volume and volume > 0:
            return True, True
    if body <= 0.20 * rng:
        return True, False
    return False, False

def detect_multi_doji_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 3:
        return False, None, None, None, None, False, None
    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]
    doji_indices = []
    prime_found = False
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        d, p = is_doji(row["open"], row["high"], row["low"], row["close"], row.get("volume"))
        if d:
            doji_indices.append(i)
            if p:
                prime_found = True
        else:
            break
    if len(doji_indices) < 2:
        return False, None, None, None, None, False, None
    doji_candles = candles.iloc[min(doji_indices):]
    body_high = max(doji_candles[["open","close"]].max())
    body_low = min(doji_candles[["open","close"]].min())
    direction = None
    if breakout_candle["high"] > body_high:
        direction = "UP ✅"
    elif breakout_candle["low"] < body_low:
        direction = "DOWN ✅"
    if not direction:
        return False, None, None, None, None, False, None
    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return True, direction, body_low, body_high, breakout_candle["close"], prime_found, bar_ts

def detect_consolidation_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 4:
        return False, None, None, None, None, None
    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]
    small_bodies = 0
    high_vals = []
    low_vals = []
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        body = abs(row["open"] - row["close"])
        rng = row["high"] - row["low"]
        if rng == 0 or body <= 0.2 * rng:
            small_bodies += 1
            high_vals.append(row["high"])
            low_vals.append(row["low"])
        else:
            break
    if small_bodies < 3:
        return False, None, None, None, None, None
    body_high = max(high_vals)
    body_low = min(low_vals)
    direction = None
    if breakout_candle["high"] > body_high:
        direction = "UP ✅"
    elif breakout_candle["low"] < body_low:
        direction = "DOWN ✅"
    if not direction:
        return False, None, None, None, None, None
    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return True, direction, body_low, body_high, breakout_candle["close"], bar_ts

# ... rest of breakout detection, plotting, telegram, crypto fetch, unchanged ...
# (You can use your existing fetch_crypto_ohlc, detect_multi_inside_breakout, scan_market, scan_crypto, scan_india functions)
# Just make sure fetch_yf_ohlc is updated as below:

def fetch_yf_ohlc(symbol, tf):
    period = "60d" if tf in ["15m","30m","1h","2h","4h"] else "730d"  # longer period for daily/weekly
    interval = tf_to_pandas(tf)
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns=str.lower)
        df["time"] = df.index.view(int) // 10**6
        return df[["open","high","low","close","volume","time"]]
    except Exception as e:
        print(f"{ist_now_str()} - Yahoo error for {symbol} ({tf}): {e}")
        return pd.DataFrame()

# Rest of your main scheduler code remains the same
if __name__ == "__main__":
    print("Starting bot...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(scan_crypto, 'interval', minutes=5, id="scan_crypto")
    scheduler.add_job(scan_india, 'interval', minutes=5, id="scan_india")
    scheduler.start()
    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("Stopping bot...")
        scheduler.shutdown()
