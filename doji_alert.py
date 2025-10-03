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

# ========================
# API Keys
# ========================
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01kg"
TELEGRAM_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
TELEGRAM_CHAT_ID = "1343842801"

# ========================
# Logging setup
# ========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ========================
# Send Telegram Alert
# ========================
def send_telegram_message(msg, image_bytes=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, data=payload)

        if image_bytes:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            files = {"photo": image_bytes}
            data = {"chat_id": TELEGRAM_CHAT_ID}
            requests.post(url, data=data, files=files)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# ========================
# Fetch Data Functions
# ========================
def fetch_yf_data(symbol, interval="15m", period="5d"):
    try:
        df = yf.download(symbol, interval=interval, period=period)
        if df is not None and not df.empty:
            df.index = df.index.tz_localize(None)
            return df
    except Exception as e:
        logging.error(f"yfinance error for {symbol}: {e}")
    return None

def fetch_alpha(symbol, interval="15min"):
    try:
        url = f"https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "apikey": ALPHA_VANTAGE_KEY,
            "datatype": "json"
        }
        r = requests.get(url, params=params).json()
        key = f"Time Series ({interval})"
        if key in r:
            df = pd.DataFrame(r[key]).T
            df = df.rename(columns={
                "1. open": "Open", "2. high": "High",
                "3. low": "Low", "4. close": "Close", "5. volume": "Volume"
            }).astype(float)
            df.index = pd.to_datetime(df.index)
            return df.sort_index()
    except Exception as e:
        logging.error(f"AlphaVantage error: {e}")
    return None

def fetch_finnhub(symbol, resolution="15"):
    try:
        url = f"https://finnhub.io/api/v1/stock/candle"
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "count": 200,
            "token": FINNHUB_KEY
        }
        r = requests.get(url, params=params).json()
        if r and r.get("s") == "ok":
            df = pd.DataFrame({
                "Open": r["o"],
                "High": r["h"],
                "Low": r["l"],
                "Close": r["c"],
                "Volume": r["v"]
            }, index=pd.to_datetime(r["t"], unit="s"))
            return df
    except Exception as e:
        logging.error(f"Finnhub error: {e}")
    return None

def fetch_data(symbol, interval="15m"):
    # Try Yahoo → Alpha → Finnhub
    df = fetch_yf_data(symbol, interval)
    if df is None or df.empty:
        logging.info(f"Yahoo failed for {symbol}, trying Alpha Vantage...")
        df = fetch_alpha(symbol)
    if (df is None or df.empty) and not symbol.startswith("^"):  # skip indices for Finnhub
        logging.info(f"Alpha failed for {symbol}, trying Finnhub...")
        df = fetch_finnhub(symbol)
    return df

# ========================
# Doji Detection
# ========================
def is_doji(candle, threshold=0.1):
    body = abs(candle["Close"] - candle["Open"])
    rng = candle["High"] - candle["Low"]
    return rng > 0 and (body / rng) < threshold

def check_doji_breakout(symbol, interval="15m"):
    df = fetch_data(symbol, interval)
    if df is None or len(df) < 5:
        return

    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]

    if is_doji(prev_candle):
        # Breakout condition: price crosses previous Doji high/low
        if last_candle["High"] > prev_candle["High"]:
            send_alert(symbol, "Bullish Doji Breakout", df)
        elif last_candle["Low"] < prev_candle["Low"]:
            send_alert(symbol, "Bearish Doji Breakout", df)

# ========================
# Plotting
# ========================
def send_alert(symbol, msg, df):
    logging.info(f"{msg} on {symbol}")
    text = f"🔥 {msg} 🔥\nSymbol: {symbol}"
    # Plot last 20 candles
    plt.figure(figsize=(8, 4))
    data = df.tail(20)
    plt.plot(data.index, data["Close"], marker="o")
    plt.title(f"{symbol} - {msg}")
    plt.grid(True)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    send_telegram_message(text, buf)
    plt.close()

# ========================
# Main Scheduler
# ========================
symbols = [
    "BTC-USD", "ETH-USD","SOL-USD","BNB-USD","XRP-USD","DOGE-USD",   # Crypto via yfinance
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS",  # Indian stocks
    "^NSEI", "^NSEBANK"     # Indices (skip Finnhub)
]

def job():
    for sym in symbols:
        try:
            check_doji_breakout(sym, "15m")
        except Exception as e:
            logging.error(f"Error on {sym}: {e}")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, "interval", minutes=5)
    scheduler.start()

    logging.info("🚀 Doji bot started. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
