import time
import requests
import pandas as pd
import numpy as np
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from binance.client import Client
from apscheduler.schedulers.background import BackgroundScheduler
import holidays
import logging
import io

# ------------------ CONFIGURATION ------------------ #

# API KEYS
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01qnmrsd01kg"

CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801", "1269772473"]

# GENERAL SETTINGS
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
HOLIDAY_LIST = holidays.India(years=datetime.now().year)
BIG_TFS = {"4h", "1d", "1w", "1M"}
TF_COOLDOWN_SEC = {
    "5m": 240, "15m": 720, "30m": 1500,
    "1h": 3300, "2h": 6600, "4h": 13200,
    "1d": 79200, "1w": 561600, "1M": 2505600
}
CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
CRYPTO_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
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

# ATR SETTINGS
ATR_PERIOD = 14
ATR_THRESHOLD = 0.005  # Example threshold for volatility filtering

# API RATE LIMIT
API_RATE_LIMITS = {
    "ALPHA_VANTAGE": {"max_calls": 5, "window_seconds": 60, "calls": 0, "last_reset": 0},
    "FINNHUB": {"max_calls": 60, "window_seconds": 60, "calls": 0, "last_reset": 0}
}

# ------------------ STATE ------------------ #
last_alert_at = {}
last_bar_key = set()
alpha_cache = {"last_time": 0, "data": {}}
finnhub_cache = {"last_time": 0, "data": {}}
BINANCE = Client()

# ------------------ LOGGING ------------------ #
logging.basicConfig(filename="bot.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ------------------ TIME UTILITIES ------------------ #
def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def is_india_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5 or now.date() in HOLIDAY_LIST:
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def cooldown_ok(market: str, symbol: str, tf: str, direction: str) -> bool:
    key = (market, symbol, tf, direction)
    now = int(datetime.now(IST).timestamp())
    cd = TF_COOLDOWN_SEC.get(tf, 600)
    last = last_alert_at.get(key, 0)
    if now - last >= cd:
        last_alert_at[key] = now
        return True
    return False

# ------------------ API RATE LIMIT ------------------ #
def check_api_limit(api_name: str) -> bool:
    limit = API_RATE_LIMITS[api_name]
    now = time.time()
    if now - limit["last_reset"] > limit["window_seconds"]:
        limit["last_reset"] = now
        limit["calls"] = 0
    if limit["calls"] < limit["max_calls"]:
        limit["calls"] += 1
        return True
    logging.warning(f"API limit exceeded for {api_name}")
    return False

# ------------------ ATR CALCULATION ------------------ #
def compute_atr(df):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    return atr.iloc[-1] if not atr.empty else 0

# ------------------ FETCHING FUNCTIONS ------------------ #
def fetch_crypto_ohlc(symbol, interval, limit=100):
    try:
        kl = BINANCE.get_klines(symbol=symbol, interval=interval, limit=limit)
        rows = [{"open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5]), "close_time": int(c[6])} for c in kl]
        return pd.DataFrame(rows)
    except Exception as e:
        logging.error(f"Binance error for {symbol}: {e}")
        return pd.DataFrame()

def fetch_yf_ohlc(symbol, tf):
    try:
        t = yf.Ticker(symbol)
        period = "1mo"
        interval = "1d"
        if tf == "15m":
            period = "7d"; interval = "15m"
        elif tf == "1h":
            period = "60d"; interval = "1h"
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            logging.warning(f"No data from Yahoo for {symbol}")
            return pd.DataFrame()
        df = hist.reset_index()
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        return df
    except Exception as e:
        logging.error(f"Yahoo Finance error for {symbol}: {e}")
        return pd.DataFrame()

# ------------------ ALERT FUNCTIONS ------------------ #
def detect_breakout(df):
    if len(df) < ATR_PERIOD + 1:
        return None
    atr = compute_atr(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    high_break = last["close"] > prev["high"] and atr > ATR_THRESHOLD * prev["close"]
    low_break = last["close"] < prev["low"] and atr > ATR_THRESHOLD * prev["close"]
    if high_break:
        return "UP BREAKOUT 🔼"
    if low_break:
        return "DOWN BREAKOUT 🔽"
    return None

def make_msg(symbol, tf, direction, low, high, last_close, prime=False, special=False):
    ts = ist_now_str()
    header = ""
    if tf in BIG_TFS:
        header += "🔶 BIG TF 🔶\n"
    if special:
        header += "🔥 SPECIAL ALERT 🔥\n"
    if prime:
        header += "🚨 PRIME 🚨\n"
    return (
        f"{header}{symbol} | {tf} | {direction}\n"
        f"Range: {low:.4f} - {high:.4f}\n"
        f"Last Price: {last_close:.4f}\n🕒 {ts} IST"
    )

def plot_chart(df, symbol, direction):
    fig, ax = plt.subplots(figsize=(6,4))
    df = df.tail(30)
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax.plot([i,i], [row["low"], row["high"]], color=color)
        ax.add_patch(plt.Rectangle((i-0.3, min(row["open"], row["close"])), 0.6, abs(row["open"]-row["close"]), color=color, alpha=0.5))
    ax.set_title(f"{symbol} {direction}")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

def send_telegram(bot_token, messages, image_buf=None):
    for chat_id in CHAT_IDS:
        try:
            if image_buf:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                files = {"photo": ("chart.png", image_buf.getvalue())}
                data = {"chat_id": chat_id, "caption": "\n".join(messages)}
                requests.post(url, data=data, files=files)
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={"chat_id": chat_id, "text": "\n".join(messages)})
        except Exception as e:
            logging.error(f"Telegram error: {e}")

# ------------------ SCANNING ------------------ #
def scan_market(symbols, tfs, bot_token, market_name):
    for symbol in symbols:
        for tf in tfs:
            if market_name == "CRYPTO":
                df = fetch_crypto_ohlc(symbol, tf)
            else:
                df = fetch_yf_ohlc(symbol, tf)
            if df.empty:
                continue
            direction = detect_breakout(df)
            if direction and cooldown_ok(market_name, symbol, tf, direction):
                last = df.iloc[-1]
                msg = make_msg(symbol, tf, direction, last["low"], last["high"], last["close"])
                buf = plot_chart(df, symbol, direction)
                send_telegram(bot_token, [msg], buf)
                logging.info(f"{symbol} {tf} {direction}")

# ------------------ MAIN ------------------ #
def main():
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(scan_crypto, 'interval', minutes=5)
    scheduler.add_job(scan_india, 'interval', minutes=5)
    scheduler.start()
    logging.info("Bot started")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

def scan_crypto():
    logging.info("Scanning crypto...")
    scan_market(CRYPTO_SYMBOLS, CRYPTO_TFS, CRYPTO_BOT_TOKEN, "CRYPTO")

def scan_india():
    if not is_india_market_hours():
        logging.info("India market closed. Skipping.")
        return
    logging.info("Scanning indices...")
    for idx_name, aliases in INDICES_MAP.items():
        for alias in aliases:
            df = fetch_yf_ohlc(alias, INDEX_TFS[0])
            if not df.empty:
                scan_market([alias], INDEX_TFS, INDIA_BOT_TOKEN, "INDIA")
                break
    logging.info("Scanning top stocks...")
    scan_market(TOP15_STOCKS_NS, STOCK_TFS, INDIA_BOT_TOKEN, "INDIA")

if __name__ == "__main__":
    main()
