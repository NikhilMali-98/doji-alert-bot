import requests
import pandas as pd
import datetime
import time
from nsepython import nsefetch

# ================== CONFIG ==================
# Crypto Bot
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CRYPTO_CHAT_IDS = ["1343842801"]

# Indian Bot
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
INDIA_CHAT_IDS = ["1343842801"]

# Crypto symbols (Binance)
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
                  "ADAUSDT", "DOGEUSDT", "MATICUSDT", "LTCUSDT", "DOTUSDT"]

# Indian indices & stocks (NSE symbols)
INDIAN_SYMBOLS = [
    "NIFTY 50", "NIFTY BANK", "SENSEX", "BANKEX",
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"
]

# Timeframes
CRYPTO_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w", "1M"]
INDIAN_TIMEFRAMES = ["10m", "15m", "1h", "4h", "1d", "1w", "1M"]

# Doji threshold
DOJI_THRESHOLD = 0.1  # %

# ============================================

def send_telegram_message(bot_token, chat_ids, message):
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": chat_id, "text": message})
        except Exception as e:
            print("Telegram Error:", e)

# ========== FETCH CRYPTO DATA ==========
def get_crypto_data(symbol, interval="15m", limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"
        ])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print(f"Crypto fetch error {symbol}:", e)
        return None

# ========== FETCH INDIAN DATA ==========
def get_indian_data(symbol):
    try:
        url = f"https://www.nseindia.com/api/chart-databyindex?index={symbol}&indices=true"
        data = nsefetch(url)
        candles = data["grapthData"][-50:]  # last 50 candles
        df = pd.DataFrame(candles, columns=["time","close"])
        # Approx O/H/L from tick data (simplified)
        df["open"] = df["close"].shift(1).fillna(df["close"])
        df["high"] = df["close"].rolling(3).max()
        df["low"] = df["close"].rolling(3).min()
        return df
    except Exception as e:
        print(f"Indian fetch error {symbol}:", e)
        return None

# ========== DOJI DETECTION ==========
def is_doji(open_price, close_price, high, low):
    if high == low:  
        return "prime"   # Division by zero case → PRIME ALERT
    body = abs(close_price - open_price)
    candle_range = high - low
    return "doji" if (body / candle_range * 100) < DOJI_THRESHOLD else None

# ========== PROCESS CANDLE ==========
def process_candles(symbol, df, bot_token, chat_ids, market_type):
    if df is None or len(df) < 2:
        return
    last = df.iloc[-1]
    prev = df.iloc[-2]

    doji_type = is_doji(prev["open"], prev["close"], prev["high"], prev["low"])
    if not doji_type:
        return

    if ((last["close"] > prev["high"]) or (last["close"] < prev["low"])):
        direction = "UP 🚀" if last["close"] > prev["high"] else "DOWN 🔻"
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST")

        if doji_type == "prime":
            msg = f"🔥🔥 PRIME {market_type} ALERT 🔥🔥\n\n"
        else:
            msg = f"🚨 {market_type} ALERT 🚨\n\n"

        msg += f"{symbol} | {direction}\n"
        msg += f"Range: {prev['low']}-{prev['high']} | Price: {last['close']}\n"
        msg += f"🕒 {ts}\n"
        msg += "━━━━━━━━━━━━━━━✦✧✦━━━━━━━━━━━━━━━"
        send_telegram_message(bot_token, chat_ids, msg)

# ========== MAIN LOOP ==========
def main():
    while True:
        # Crypto
        for sym in CRYPTO_SYMBOLS:
            for tf in CRYPTO_TIMEFRAMES:
                df = get_crypto_data(sym, tf)
                process_candles(sym, df, CRYPTO_BOT_TOKEN, CRYPTO_CHAT_IDS, "CRYPTO")
                time.sleep(1)

        # Indian
        for sym in INDIAN_SYMBOLS:
            df = get_indian_data(sym)
            process_candles(sym, df, INDIA_BOT_TOKEN, INDIA_CHAT_IDS, "INDIA")
            time.sleep(1)

        time.sleep(60)  # run every min

if __name__ == "__main__":
    main()
