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
    "5m": 240, "15m": 720, "30m": 1500,
    "1h": 3300, "2h": 6600, "4h": 13200,
    "1d": 79200, "1w": 561600, "1M": 2505600
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
INDEX_TFS = ["15m", "1h", "2h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "2h", "4h", "1d", "1w", "1M"]
BINANCE_INTERVALS = {
    "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h",
    "2h": "2h", "4h": "4h", "1d": "1d", "1w": "1w", "1M": "1M"
}

BINANCE = Client()

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
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def tf_to_pandas(tf: str) -> str:
    return {
        "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "2h": "2h", "4h": "4h",
        "1d": "1D", "1w": "1W", "1M": "1M"
    }[tf]

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
    if df_ohlc.empty or df_ohlc.isnull().all().all() or len(df_ohlc) < 3:
        return False, None, None, None, None, False, None
    candles = df_ohlc.iloc[:-1].dropna(subset=["open","high","low","close"])
    breakout_candle = df_ohlc.iloc[-1]
    if any(pd.isna([breakout_candle.get("open"), breakout_candle.get("high"),
                    breakout_candle.get("low"), breakout_candle.get("close")])):
        return False, None, None, None, None, False, None
    doji_indices = []
    prime_found = False
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        if any(pd.isna([row.get("open"), row.get("high"), row.get("low"), row.get("close")])):
            continue
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
    body_low  = min(doji_candles[["open","close"]].min())
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
    if df_ohlc.empty or df_ohlc.isnull().all().all() or len(df_ohlc) < 5:
        return False, None, None, None, None, None, None
    candles = df_ohlc.iloc[:-1].dropna(subset=["open","high","low","close"])
    breakout_candle = df_ohlc.iloc[-1]
    if any(pd.isna([breakout_candle.get("open"), breakout_candle.get("high"),
                    breakout_candle.get("low"), breakout_candle.get("close")])):
        return False, None, None, None, None, None, None
    body_high = max(candles[["open","close"]].max())
    body_low  = min(candles[["open","close"]].min())
    rng = body_high - body_low
    if rng / breakout_candle["close"] > 0.005:
        return False, None, None, None, None, None, None
    direction = None
    if breakout_candle["high"] > body_high:
        direction = "UP 🔥"
    elif breakout_candle["low"] < body_low:
        direction = "DOWN 🔥"
    if not direction:
        return False, None, None, None, None, None, None
    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return True, direction, body_low, body_high, breakout_candle["close"], True, bar_ts

def detect_multi_inside_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc.empty or df_ohlc.isnull().all().all() or len(df_ohlc) < 3:
        return False, None, None, None, None, None, None
    candles = df_ohlc.iloc[:-1].dropna(subset=["open","high","low","close"])
    breakout_candle = df_ohlc.iloc[-1]
    if any(pd.isna([breakout_candle.get("open"), breakout_candle.get("high"),
                    breakout_candle.get("low"), breakout_candle.get("close")])):
        return False, None, None, None, None, None, None
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        if any(pd.isna([row.get("open"), row.get("high"), row.get("low"), row.get("close")])):
            continue
        high = row["high"]
        low = row["low"]
        if breakout_candle["high"] > high or breakout_candle["low"] < low:
            direction = "UP 🔼" if breakout_candle["high"] > high else "DOWN 🔽"
            bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
            return True, direction, low, high, breakout_candle["close"], True, bar_ts
    return False, None, None, None, None, None, None

def fetch_stock_ohlc(symbol: str, tf: str, period="30d"):
    interval = tf_to_pandas(tf)
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"}, inplace=True)
    df.reset_index(inplace=True)
    df["time"] = df["Datetime"].astype(int) // 10**9
    df["close_time"] = df["time"]
    return df

def fetch_crypto_ohlc(symbol: str, tf: str, limit=50):
    interval = BINANCE_INTERVALS.get(tf)
    klines = BINANCE.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=["open_time","open","high","low","close","volume",
                                       "close_time","quote_asset_volume","number_of_trades",
                                       "taker_buy_base_asset_volume","taker_buy_quote_asset_volume","ignore"])
    df = df.astype({
        "open":"float", "high":"float", "low":"float", "close":"float", "volume":"float"
    })
    return df

def plot_chart(df, low, high, title):
    plt.figure(figsize=(10,5))
    plt.plot(df["close"], label="Close")
    plt.axhline(low, color='red', linestyle='--')
    plt.axhline(high, color='green', linestyle='--')
    plt.title(title)
    plt.legend()
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf

def scan_market(market: str, symbols: list, tfs: list, bot_token: str):
    for symbol in symbols:
        for tf in tfs:
            try:
                period = "30d" if tf in BIG_TFS else "7d"
                if market == "CRYPTO":
                    df = fetch_crypto_ohlc(symbol, tf)
                else:
                    df = fetch_stock_ohlc(symbol, tf, period=period)
                if df.empty or df.isnull().all().all():
                    print(f"{ist_now_str()} - Skipping {symbol} {tf}, invalid data")
                    continue
                for detect_func, name in [
                    (detect_multi_doji_breakout, "Multi Doji Breakout"),
                    (detect_consolidation_breakout, "Consolidation Breakout"),
                    (detect_multi_inside_breakout, "Inside Candle Breakout")
                ]:
                    trig, direction, low, high, last_close, prime, bar_ts = detect_func(df)
                    if trig and cooldown_ok(market, symbol, tf, direction):
                        msg = f"{name} - {symbol} {tf} {direction}\nPrice: {last_close}\nTime: {ist_now_str()}"
                        img_buf = plot_chart(df, low, high, f"{symbol} {tf} {name}")
                        send_telegram(bot_token, [msg], img_buf)
            except Exception as e:
                print(f"{ist_now_str()} - Error scanning {symbol} {tf}: {e}")

def scan_crypto():
    print(f"{ist_now_str()} - Scanning crypto market")
    scan_market("CRYPTO", CRYPTO_SYMBOLS, CRYPTO_TFS, CRYPTO_BOT_TOKEN)

def scan_india():
    print(f"{ist_now_str()} - Scanning stocks")
    if not is_india_market_hours():
        print(f"{ist_now_str()} - Market closed")
        return
    scan_market("INDIA_STOCKS", TOP15_STOCKS_NS, STOCK_TFS, INDIA_BOT_TOKEN)

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(scan_crypto, "interval", minutes=5, next_run_time=datetime.now())
    scheduler.add_job(scan_india, "interval", minutes=5, next_run_time=datetime.now())
    scheduler.start()
    print("Scheduler started...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Stopping...")
        scheduler.shutdown()
