import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
import io
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler

# ==============================
# 🔑 API Keys
# ==============================
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01qnmrsd01kg"
TELEGRAM_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
TELEGRAM_CHAT_ID = "1343842801"

# ==============================
# ⚙️ Logging
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ==============================
# ⏰ Timezones
# ==============================
IST = pytz.timezone("Asia/Kolkata")

# ==============================
# 🛑 Binance Fix
# ==============================
class DummyBinance:
    def __init__(self):
        pass

BINANCE = DummyBinance()  # placeholder to avoid crashes


# ==============================
# 📊 Data Fetchers
# ==============================
def fetch_crypto_data(symbol, interval, lookback=200):
    """
    Fetch crypto data using yfinance instead of Binance (PythonAnywhere restriction fix).
    """
    try:
        ticker = symbol.replace("/", "") + "-USD" if "/" in symbol else symbol + "-USD"
        yf_interval_map = {
            "15m": "15m",
            "30m": "30m",
            "1h": "60m",
            "2h": "120m",
            "4h": "240m",
            "1d": "1d",
            "1w": "1wk",
            "1M": "1mo",
        }
        df = yf.download(ticker, period="60d", interval=yf_interval_map[interval])
        if df.empty:
            return pd.DataFrame()
        df = df.tail(lookback)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logging.error(f"Crypto fetch failed for {symbol} ({interval}): {e}")
        return pd.DataFrame()


def fetch_stock_data(symbol, interval, lookback=200):
    """
    Fetch stock/indices data using yfinance.
    """
    try:
        yf_interval_map = {
            "15m": "15m",
            "30m": "30m",
            "1h": "60m",
            "2h": "120m",
            "4h": "240m",
            "1d": "1d",
            "1w": "1wk",
            "1M": "1mo",
        }
        df = yf.download(symbol, period="60d", interval=yf_interval_map[interval])
        if df.empty:
            return pd.DataFrame()
        df = df.tail(lookback)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logging.error(f"Stock fetch failed for {symbol} ({interval}): {e}")
        return pd.DataFrame()


# ==============================
# 📐 Indicators
# ==============================
def atr(df, period=14):
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift(1))
    df["L-PC"] = abs(df["Low"] - df["Close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(period).mean()
    return df


def is_doji(candle, threshold=0.1):
    body = abs(candle["Close"] - candle["Open"])
    candle_range = candle["High"] - candle["Low"]
    return body <= threshold * candle_range


# ==============================
# 🔔 Alerts
# ==============================
def send_telegram_alert(message, chart=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}

        if chart is None:
            requests.post(url, data=payload)
        else:
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            files = {"photo": chart}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": message, "parse_mode": "HTML"}
            requests.post(photo_url, data=data, files=files)

    except Exception as e:
        logging.error(f"Telegram alert failed: {e}")


def plot_doji_chart(df, symbol, title, breakout_level=None, range_zone=None):
    plt.figure(figsize=(10, 5))
    plt.plot(df.index, df["Close"], label="Close", color="blue")
    plt.title(f"{symbol} - {title}")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend()

    if breakout_level:
        plt.axhline(breakout_level, color="red", linestyle="--", label="Breakout")
    if range_zone:
        plt.axhspan(range_zone[0], range_zone[1], color="yellow", alpha=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf


# ==============================
# 🚨 Strategies
# ==============================
def check_doji_breakout(df, symbol, interval):
    if len(df) < 20:
        return
    df = atr(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if is_doji(prev) and not is_doji(last):
        breakout = None
        if last["Close"] > prev["High"]:
            breakout = "Bullish Doji Breakout"
        elif last["Close"] < prev["Low"]:
            breakout = "Bearish Doji Breakdown"

        if breakout:
            chart = plot_doji_chart(df, symbol, breakout, breakout_level=prev["High"] if "Bullish" in breakout else prev["Low"])
            send_telegram_alert(f"🔥 {breakout} on {symbol} ({interval})", chart)


def check_consolidation_breakout(df, symbol, interval):
    if len(df) < 20:
        return
    df = atr(df)

    last = df.iloc[-1]
    prev10 = df.iloc[-6:-1]

    small_bodies = all(is_doji(c, 0.2) for _, c in prev10.iterrows())
    if small_bodies:
        breakout = None
        if last["Close"] > prev10["High"].max():
            breakout = "Bullish Consolidation Breakout"
        elif last["Close"] < prev10["Low"].min():
            breakout = "Bearish Consolidation Breakdown"

        if breakout:
            chart = plot_doji_chart(df, symbol, breakout, range_zone=(prev10["Low"].min(), prev10["High"].max()))
            send_telegram_alert(f"🔥 {breakout} on {symbol} ({interval})", chart)


def check_inside_candle_breakout(df, symbol, interval):
    if len(df) < 20:
        return
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["High"] < prev["High"] and last["Low"] > prev["Low"]:
        # Inside candle detected
        breakout = None
        if df.iloc[-3]["Close"] > prev["High"]:
            breakout = "Bullish Inside Candle Breakout"
        elif df.iloc[-3]["Close"] < prev["Low"]:
            breakout = "Bearish Inside Candle Breakdown"

        if breakout:
            chart = plot_doji_chart(df, symbol, breakout, range_zone=(prev["Low"], prev["High"]))
            send_telegram_alert(f"🔥 {breakout} on {symbol} ({interval})", chart)


# ==============================
# 📅 Scheduler
# ==============================
def run_scan():
    logging.info("Running market scan...")

    CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
    STOCK_SYMBOLS = ["^NSEI", "^NSEBANK", "RELIANCE.NS", "TCS.NS"]

    TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d"]

    for sym in CRYPTO_SYMBOLS:
        for tf in TIMEFRAMES:
            df = fetch_crypto_data(sym, tf)
            if not df.empty:
                check_doji_breakout(df, sym, tf)
                check_consolidation_breakout(df, sym, tf)
                check_inside_candle_breakout(df, sym, tf)

    for sym in STOCK_SYMBOLS:
        for tf in TIMEFRAMES:
            df = fetch_stock_data(sym, tf)
            if not df.empty:
                check_doji_breakout(df, sym, tf)
                check_consolidation_breakout(df, sym, tf)
                check_inside_candle_breakout(df, sym, tf)


# ==============================
# 🚀 Main
# ==============================
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scan, "interval", minutes=5)
    scheduler.start()

    logging.info("Doji Alert Bot started (PythonAnywhere safe mode)...")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logging.info("Bot stopped.")

