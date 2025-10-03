

import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import io
import logging
import numpy as np

# ================= CONFIG =================
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01kg"
TELEGRAM_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
TELEGRAM_CHAT_ID = "1343842801"

# Symbols
CRYPTO_LIST = ["BTC-USD", "ETH-USD","SOL-USD","BNB-USD","XRP-USD","DOGE-USD"]
INDIAN_STOCKS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
INDICES = ["^NSEI", "^NSEBANK"]

TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d"]

# ATR config
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ================= TELEGRAM =================
def send_telegram_message(text, chart_path=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        if chart_path:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(chart_path, "rb") as f:
                requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID}, files={"photo": f})
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# ================= DATA FETCH =================
def fetch_crypto(symbol, interval="15m", limit=200):
    try:
        data = yf.download(symbol, period="7d", interval=interval)
        if not data.empty:
            return data.tail(limit)
    except Exception as e:
        logging.error(f"Error fetching crypto {symbol}: {e}")
    return None

def fetch_stock(symbol, interval="15m", limit=200):
    try:
        if symbol in INDICES and interval in ["15m","30m","60m"]:
            logging.info(f"Skipping {symbol} {interval} (unsupported)")
            return None
        data = yf.download(symbol, period="60d", interval=interval)
        if not data.empty:
            return data.tail(limit)
    except Exception as e:
        logging.error(f"Error fetching stock {symbol}: {e}")
    return None

# ================= INDICATORS =================
def is_doji(candle):
    body = abs(candle["Close"] - candle["Open"])
    avg = (candle["High"] - candle["Low"])
    return body <= 0.1 * avg

def calculate_atr(df, period=ATR_PERIOD):
    df["H-L"] = df["High"] - df["Low"]
    df["H-C"] = abs(df["High"] - df["Close"].shift())
    df["L-C"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-C", "L-C"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(period).mean()
    return df

def check_consolidation(df, n=4):
    last = df.tail(n)
    return all(abs(row["Close"]-row["Open"]) <= 0.2*(row["High"]-row["Low"]) for _,row in last.iterrows())

def check_inside_candle(df):
    if len(df) < 3: return False
    prev, curr = df.iloc[-2], df.iloc[-1]
    return curr["High"] <= prev["High"] and curr["Low"] >= prev["Low"]

# ================= PLOTTING =================
def plot_chart(df, title, breakout=None):
    plt.figure(figsize=(8,4))
    plt.plot(df.index, df["Close"], label="Close")
    if breakout:
        plt.axhline(breakout, color="red", linestyle="--")
    plt.title(title)
    plt.legend()
    path = f"chart_{title.replace('/','_')}.png"
    plt.savefig(path)
    plt.close()
    return path

# ================= ALERTS =================
def process_symbol(symbol, interval, market="crypto"):
    df = fetch_crypto(symbol, interval) if market=="crypto" else fetch_stock(symbol, interval)
    if df is None or df.empty: return
    df = calculate_atr(df)

    latest = df.iloc[-1]

    # Doji breakout
    if is_doji(df.iloc[-2]):
        if latest["High"] > df.iloc[-2]["High"]:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=df.iloc[-2]["High"])
            send_telegram_message(f"📌 Doji Breakout UP {symbol} {interval}", chart)

        elif latest["Low"] < df.iloc[-2]["Low"]:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=df.iloc[-2]["Low"])
            send_telegram_message(f"📌 Doji Breakout DOWN {symbol} {interval}", chart)

    # Consolidation breakout
    if check_consolidation(df):
        rng_high, rng_low = df.iloc[-5:-1]["High"].max(), df.iloc[-5:-1]["Low"].min()
        if latest["High"] > rng_high:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=rng_high)
            send_telegram_message(f"🔥 Consolidation Breakout UP {symbol} {interval}", chart)
        elif latest["Low"] < rng_low:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=rng_low)
            send_telegram_message(f"🔥 Consolidation Breakout DOWN {symbol} {interval}", chart)

    # Inside candle breakout
    if check_inside_candle(df):
        prev = df.iloc[-2]
        if latest["High"] > prev["High"]:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=prev["High"])
            send_telegram_message(f"🔔 Inside Candle Breakout UP {symbol} {interval}", chart)
        elif latest["Low"] < prev["Low"]:
            chart = plot_chart(df.tail(50), f"{symbol}_{interval}", breakout=prev["Low"])
            send_telegram_message(f"🔔 Inside Candle Breakout DOWN {symbol} {interval}", chart)

# ================= SCHEDULER =================
def run_all():
    for tf in TIMEFRAMES:
        for c in CRYPTO_LIST:
            process_symbol(c, tf, "crypto")
        for s in INDIAN_STOCKS + INDICES:
            process_symbol(s, tf, "stock")

if __name__ == "__main__":
    logging.info("🚀 Bot started...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_all, "interval", minutes=5)
    scheduler.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logging.info("Bot stopped.")
