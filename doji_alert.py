import time
import datetime
import pytz
import pandas as pd
import ccxt
import requests
import traceback
import yfinance as yf
from nsepython import nse_get_index_list, nse_quote

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Crypto setup (Binance)
exchange = ccxt.binance()

# Avoid duplicate alerts
last_alerts = {}

# Timeframes
TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "1d"]

# Indian market symbols
NSE_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
BSE_STOCKS = ["500325.BO", "500112.BO"]  # Example BSE codes

# =====================
# 🔹 Telegram Bots
# =====================
CRYPTO_BOT_TOKEN ="7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CRYPTO_CHAT_ID = "1343842801"

INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
INDIA_CHAT_ID = "1343842801"



def send_telegram_message(bot_token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def get_crypto_data(symbol, timeframe="15m", limit=5):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching crypto {symbol}: {e}")
        return None


def get_nse_data(symbol):
    try:
        q = nse_quote(symbol)
        return {
            "symbol": symbol,
            "price": float(q["priceInfo"]["lastPrice"]),
            "high": float(q["priceInfo"]["intraDayHighLow"]["max"]),
            "low": float(q["priceInfo"]["intraDayHighLow"]["min"]),
        }
    except Exception as e:
        print(f"NSE fetch error {symbol}: {e}")
        return None


def get_bse_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="5m")
        if not data.empty:
            latest = data.iloc[-1]
            return {
                "symbol": symbol,
                "price": latest["Close"],
                "high": data["High"].max(),
                "low": data["Low"].min(),
            }
        return None
    except Exception as e:
        print(f"BSE fetch error {symbol}: {e}")
        return None


def is_doji(open_, close, high, low, threshold=0.1):
    body = abs(close - open_)
    range_ = high - low
    return body <= threshold * range_


def format_alert(symbol, tf, direction, low, high, price):
    now = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    msg = f"""🚨 {symbol} | {tf} | {direction} 🚀
Range: {low:.4f}-{high:.4f} | Price: {price:.4f}
🕒 {now}
━━━━━━━✦✧✦━━━━━━━"""
    return msg


def check_and_alert(symbol, tf, open_, close, high, low, is_crypto=True):
    direction = "UP" if close > open_ else "DOWN"
    if is_doji(open_, close, high, low):
        msg = format_alert(symbol, tf, direction, low, high, close)
        key = f"{symbol}-{tf}-{direction}"
        now = time.time()

        # Prevent spam: 5 min cooldown per symbol+tf+direction
        if key not in last_alerts or now - last_alerts[key] > 300:
            last_alerts[key] = now

            if is_crypto:
                send_telegram_message(CRYPTO_BOT_TOKEN, CRYPTO_CHAT_ID, msg)
            else:
                send_telegram_message(INDIA_BOT_TOKEN, INDIA_CHAT_ID, msg)


def run():
    while True:
        try:
            # 🔹 Crypto Alerts
            for sym in ["XRP/USDT", "BTC/USDT", "ETH/USDT"]:
                for tf in TIMEFRAMES:
                    df = get_crypto_data(sym, tf)
                    if df is not None and len(df) >= 2:
                        row = df.iloc[-1]
                        check_and_alert(
                            sym.replace("/", ""),
                            tf,
                            row["open"],
                            row["close"],
                            row["high"],
                            row["low"],
                            is_crypto=True,
                        )

            # 🔹 NSE Alerts
            for sym in NSE_STOCKS:
                data = get_nse_data(sym)
                if data:
                    check_and_alert(sym, "Spot", data["price"], data["price"], data["high"], data["low"], is_crypto=False)

            # 🔹 BSE Alerts
            for sym in BSE_STOCKS:
                data = get_bse_data(sym)
                if data:
                    check_and_alert(sym, "Spot", data["price"], data["price"], data["high"], data["low"], is_crypto=False)

        except Exception as e:
            print("Error in main loop:", e)
            traceback.print_exc()

        time.sleep(300)  # run every 5 min


if __name__ == "__main__":
    run()
