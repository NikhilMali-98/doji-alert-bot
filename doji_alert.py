import os
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pytz
import io
import logging

# Telegram Bot Configuration
TELEGRAM_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
TELEGRAM_CHAT_ID = "134384280"

# API Keys (for Alpha Vantage, Finnhub fallback if needed)
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01kg"

# Logging Setup
logging.basicConfig(filename="bot_log.txt", level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d"]
CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD"]
INDIAN_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "ICICIBANK.NS"]

IST = pytz.timezone("Asia/Kolkata")


# --- Helper: Send Telegram Message ---
def send_telegram_message(msg, chart_img=None):
    try:
        if chart_img:
            files = {"photo": chart_img}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": msg}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        logging.error(f"Telegram send error: {e}")


# --- ATR Calculation ---
def calculate_atr(df, period=14):
    df["H-L"] = df["High"] - df["Low"]
    df["H-C"] = abs(df["High"] - df["Close"].shift(1))
    df["L-C"] = abs(df["Low"] - df["Close"].shift(1))
    df["TR"] = df[["H-L", "H-C", "L-C"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(window=period).mean()
    return df


# --- Fetch Data Function (YFinance Fallback for All) ---
def fetch_data(symbol, interval="1h", limit=100):
    try:
        df = yf.download(symbol, period="5d", interval=interval, progress=False)
        df = df.dropna()
        df = df.reset_index()
        df.rename(columns={"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"}, inplace=True)
        return df
    except Exception as e:
        logging.error(f"Data fetch error for {symbol}: {e}")
        return pd.DataFrame()


# --- Doji Detection ---
def is_doji(df, threshold=0.1):
    body = abs(df["Close"] - df["Open"])
    candle_range = df["High"] - df["Low"]
    return (body / candle_range) < threshold


# --- Consolidation Detection ---
def is_consolidation(df, num_candles=4, threshold=0.3):
    recent = df[-num_candles:]
    body_sizes = abs(recent["Close"] - recent["Open"])
    avg_range = recent["High"].max() - recent["Low"].min()
    return body_sizes.mean() / avg_range < threshold


# --- Inside Candle Detection ---
def is_inside_candle(df):
    if len(df) < 3:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    return curr["High"] < prev["High"] and curr["Low"] > prev["Low"]


# --- Plot Chart ---
def plot_chart(df, symbol, title, breakout_level=None):
    plt.figure(figsize=(8, 4))
    plt.plot(df["Date"], df["Close"], label="Close", lw=1.2)
    if breakout_level:
        plt.axhline(y=breakout_level, color="orange", linestyle="--", label="Breakout")
    plt.title(f"{symbol} - {title}")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf


# --- Check Alerts ---
def check_alerts(symbol, df):
    msg = None
    chart_img = None

    df = calculate_atr(df)

    if is_doji(df.iloc[-1]):
        msg = f"⚡ DOJI ALERT ⚡\nSymbol: {symbol}\nPossible breakout setup!"
        chart_img = plot_chart(df, symbol, "Doji Alert")

    elif is_consolidation(df):
        msg = f"🔥 CONSOLIDATION ALERT 🔥\nSymbol: {symbol}\nTight range breakout possible."
        chart_img = plot_chart(df, symbol, "Consolidation Alert")

    elif is_inside_candle(df):
        msg = f"📦 INSIDE CANDLE ALERT 📦\nSymbol: {symbol}\nBreakout nearing soon."
        chart_img = plot_chart(df, symbol, "Inside Candle")

    if msg:
        send_telegram_message(msg, chart_img)
        logging.info(f"Alert sent for {symbol}: {msg}")


# --- Main Loop ---
def main_loop():
    while True:
        now = datetime.now(IST)
        logging.info(f"Scanning at {now.strftime('%H:%M:%S')}...")

        for sym in CRYPTO_SYMBOLS + INDIAN_SYMBOLS:
            for tf in TIMEFRAMES:
                df = fetch_data(sym, interval=tf)
                if not df.empty:
                    check_alerts(sym, df)
                time.sleep(2)  # Avoid hitting limits

        logging.info("Scan cycle complete. Sleeping 10 minutes...")
        time.sleep(600)


if __name__ == "__main__":
    print("🚀 Bot started successfully — Binance removed (Yahoo data in use).")
    logging.info("Bot started successfully.")
    main_loop()
