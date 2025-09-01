import os
import time
import ccxt
import pandas as pd
import numpy as np
import requests
import pytz
from datetime import datetime
from nsepython import nse_index, nse_quote

# ========== CONFIG ==========
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

# Binance client
exchange = ccxt.binance()

# Timeframes
CRYPTO_TF = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]
INDICES = ["NIFTY 50", "NIFTY BANK", "SENSEX", "BSE BANKEX"]
STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]

# Highlight bigger TFs
HIGHLIGHT_TF = ["4h", "1d", "1w", "1M"]

# ========== UTILS ==========
def send_telegram(bot_token, text):
    for cid in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, data={"chat_id": cid, "text": text})
        except Exception as e:
            print(f"Telegram error: {e}")

def is_market_open():
    """Check NSE/BSE market hours (Mon–Fri, 9:15–15:30 IST)."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def detect_doji(candle):
    o, h, l, c = candle
    body = abs(c - o)
    rng = h - l if h != l else 1
    if rng == 0:
        return False, False
    body_pct = body / rng * 100
    prime = body_pct < 0.5  # almost open=close
    is_doji = body_pct < 10
    return is_doji, prime

# ========== CRYPTO PART ==========
def check_crypto():
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        for tf in CRYPTO_TF:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
                o, h, l, c = ohlcv[-1][1:5]
                is_doji, prime = detect_doji((o, h, l, c))
                if is_doji:
                    hl = "⚡" if tf in HIGHLIGHT_TF else ""
                    prime_tag = "🔥 Prime Doji" if prime else "Doji"
                    msg = f"{hl} {prime_tag} in {symbol} {tf} | O:{o} C:{c} H:{h} L:{l}"
                    send_telegram(CRYPTO_BOT_TOKEN, msg)
            except Exception as e:
                print(f"Crypto error {symbol}-{tf}: {e}")

# ========== INDIAN MARKET PART ==========
def check_indices():
    try:
        idx_data = nse_index()
        for idx in INDICES:
            data = next((i for i in idx_data if i.get("indexName") == idx), None)
            if not data:
                continue
            o = data.get("dayHigh")  # NSE index data has no proper OHLC intraday, fallback
            c = data.get("last")
            h = data.get("yearHigh")
            l = data.get("yearLow")
            if not all([o, c, h, l]):
                continue
            is_doji, prime = detect_doji((o, h, l, c))
            if is_doji:
                prime_tag = "🔥 Prime Doji" if prime else "Doji"
                msg = f"📊 {prime_tag} in {idx} | O:{o} C:{c} H:{h} L:{l}"
                send_telegram(INDIA_BOT_TOKEN, msg)
    except Exception as e:
        print(f"Index error: {e}")

def check_stocks():
    for stock in STOCKS:
        try:
            data = nse_quote(stock)
            o = data.get("dayHigh")
            c = data.get("lastPrice")
            h = data.get("dayHigh")
            l = data.get("dayLow")
            if not all([o, c, h, l]):
                continue
            is_doji, prime = detect_doji((o, h, l, c))
            if is_doji:
                prime_tag = "🔥 Prime Doji" if prime else "Doji"
                msg = f"📈 {prime_tag} in {stock} | O:{o} C:{c} H:{h} L:{l}"
                send_telegram(INDIA_BOT_TOKEN, msg)
        except Exception as e:
            print(f"Stock error {stock}: {e}")

# ========== MAIN LOOP ==========
if __name__ == "__main__":
    while True:
        check_crypto()
        if is_market_open():
            check_indices()
            check_stocks()
        time.sleep(300)  # run every 5 min
