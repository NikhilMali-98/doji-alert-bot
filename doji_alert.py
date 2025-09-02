import os
import time
import ccxt
import requests
import pytz
from datetime import datetime
from nsepython import nse_index_list, nse_quote

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

# Cache for last alerts
last_alerts = {}
alert_cooldown = 300  # 10 minutes between alerts for same key


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


def format_msg(symbol, tf, o, h, l, c, prime, bot="crypto"):
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).strftime("%Y-%m-%d %H:%M IST")
    hl = "🚨 " if tf in HIGHLIGHT_TF else ""
    arrow = "🚀" if c > o else "🔻"
    tag = "🔥 Prime Doji" if prime else "Doji"

    msg = (
        f"{hl}{symbol} | {tf} | {tag} {arrow}\n"
        f"Range: {round(l,4)}-{round(h,4)} | Price: {round(c,4)}\n"
        f"🕒 {now}\n"
        f"━━━━✦✧✦━━━━"
    )
    return msg


def should_alert(key, new_val):
    """Avoid repeated alerts for same symbol+tf with cooldown."""
    global last_alerts
    now = time.time()
    if key not in last_alerts or (now - last_alerts[key]["time"] > alert_cooldown):
        last_alerts[key] = {"val": new_val, "time": now}
        return True
    return False


# ========== CRYPTO PART ==========
def check_crypto():
    for symbol in ["BTC/USDT", "ETH/USDT", "XRP/USDT"]:
        for tf in CRYPTO_TF:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
                o, h, l, c = ohlcv[-1][1:5]
                is_doji, prime = detect_doji((o, h, l, c))
                if is_doji:
                    msg_key = f"crypto-{symbol}-{tf}"
                    msg_val = f"{o}-{c}-{h}-{l}"
                    if should_alert(msg_key, msg_val):
                        msg = format_msg(symbol, tf, o, h, l, c, prime, bot="crypto")
                        send_telegram(CRYPTO_BOT_TOKEN, msg)
            except Exception as e:
                print(f"Crypto error {symbol}-{tf}: {e}")


# ========== INDIAN MARKET PART ==========
def check_indices():
    try:
        idx_data = nse_index_list()
        for idx in INDICES:
            data = next((i for i in idx_data if i.get("indexName") == idx), None)
            if not data:
                continue
            o = data.get("dayHigh") or 0
            c = data.get("last") or 0
            h = data.get("yearHigh") or 0
            l = data.get("yearLow") or 0
            if not all([o, c, h, l]):
                continue
            is_doji, prime = detect_doji((o, h, l, c))
            if is_doji:
                msg_key = f"index-{idx}"
                msg_val = f"{o}-{c}-{h}-{l}"
                if should_alert(msg_key, msg_val):
                    msg = format_msg(idx, "LIVE", o, h, l, c, prime, bot="india")
                    send_telegram(INDIA_BOT_TOKEN, msg)
    except Exception as e:
        print(f"Index error: {e}")


def check_stocks():
    for stock in STOCKS:
        try:
            data = nse_quote(stock)
            o = data.get("dayHigh") or 0
            c = data.get("lastPrice") or 0
            h = data.get("dayHigh") or 0
            l = data.get("dayLow") or 0
            if not all([o, c, h, l]):
                continue
            is_doji, prime = detect_doji((o, h, l, c))
            if is_doji:
                msg_key = f"stock-{stock}"
                msg_val = f"{o}-{c}-{h}-{l}"
                if should_alert(msg_key, msg_val):
                    msg = format_msg(stock, "LIVE", o, h, l, c, prime, bot="india")
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
