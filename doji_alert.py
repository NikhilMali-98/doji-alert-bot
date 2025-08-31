import requests
import pandas as pd
import datetime
import pytz
import time
import yfinance as yf

# 📌 Telegram Details
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
CRYPTO_CHAT_IDS = ["1343842801"]

INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
INDIA_CHAT_IDS = ["1343842801"]

# 📌 Binance API
CRYPTO_API = "https://api.binance.com/api/v3/klines"

# 📌 Crypto List (Top 10)
CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
                  "DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","MATICUSDT"]

# 📌 Crypto Timeframes
CRYPTO_TIMEFRAMES = ["15m","30m","1h","2h","4h","1d"]
SPECIAL_5M = ["BTCUSDT","ETHUSDT","SOLUSDT"]

# 📌 NSE Stocks + Indices + Sensex + Bankex
INDIAN_SYMBOLS = [
    "RELIANCE.NS","HDFCBANK.NS","TCS.NS","INFY.NS","ICICIBANK.NS",
    "SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS","LT.NS","HINDUNILVR.NS",
    "AXISBANK.NS","ITC.NS","BAJFINANCE.NS","WIPRO.NS","MARUTI.NS",
    "^NSEI","^NSEBANK","^BSESN","^BSEBANK"  # NIFTY, BANKNIFTY, SENSEX, BANKEX
]

# 📌 Indian Timeframes
INDIA_TIMEFRAMES = ["10m","15m","1h","3h","4h","1d","1w","1mo"]

# Function: Send Telegram Msg
def send_telegram(bot_token, chat_ids, message):
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, data=payload)
        except Exception as e:
            print("Telegram Error:", e)

# Function: Fetch Crypto OHLC
def get_crypto_data(symbol, interval, limit=10):
    try:
        url = f"{CRYPTO_API}?symbol={symbol}&interval={interval}&limit={limit}"
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume","_","__","___","____","_____","______"
        ])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print(f"Crypto Fetch Error {symbol}:", e)
        return None

# Function: Fetch Indian Stock OHLC
def get_indian_data(symbol, interval="15m", limit=20):
    try:
        df = yf.download(tickers=symbol, period="6mo", interval=interval, progress=False)
        df = df.tail(limit)
        df.reset_index(inplace=True)
        df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"}, inplace=True)
        return df
    except Exception as e:
        print(f"Indian Data Fetch Error {symbol}:", e)
        return None

# Function: Detect Doji
def is_doji(candle):
    try:
        body = abs(candle["close"] - candle["open"])
        candle_range = candle["high"] - candle["low"]
        if candle_range == 0:
            return "prime"
        return body <= (0.2 * candle_range)
    except:
        return False

# Function: Analyze
def analyze_data(df, symbol, tf, market="crypto"):
    if df is None or len(df) < 6:
        return None
    
    last5 = df.tail(5).reset_index(drop=True)
    dojis = []
    for i in range(4):  # check last 4 candles
        res = is_doji(last5.iloc[i])
        if res: dojis.append(res)
    
    # ✅ Prime confirmation = Last candle must not be doji
    last = last5.iloc[-1]
    last_doji = is_doji(last)
    if len(dojis) >= 2 and not last_doji:
        prev = last5.iloc[:-1]

        direction = None
        if last["close"] > prev["close"].max():
            direction = "UP 🚀"
        elif last["close"] < prev["close"].min():
            direction = "DOWN 🔻"

        if direction:
            tz = pytz.timezone("Asia/Kolkata")
            now = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M")
            rng = f"{round(prev['open'].min(),2)} - {round(prev['close'].max(),2)}"

            # Separator
            sep = "\n━━━━━━━━━━━━━━━✦✧✦━━━━━━━━━━━━━━━\n"

            # Prime message highlight
            if "prime" in dojis:
                msg = f"🔥 PRIME BREAKOUT 🔥{sep}\n"
            else:
                msg = f"🚨 Alert {sep}\n"

            # Symbol adjust
            if market == "crypto":
                sym = symbol.replace("USDT","USD")
            else:
                sym = symbol.replace(".NS","") \
                           .replace("^NSEI","NIFTY") \
                           .replace("^NSEBANK","BANKNIFTY") \
                           .replace("^BSESN","SENSEX") \
                           .replace("^BSEBANK","BANKEX")

            msg += f"{sym} | {tf} | {direction}\n"
            msg += f"Range: {rng} | Price: {round(last['close'],2)}\n"
            msg += f"🕒 {now} IST"

            if market == "crypto":
                send_telegram(CRYPTO_BOT_TOKEN, CRYPTO_CHAT_IDS, msg)
            else:
                send_telegram(INDIA_BOT_TOKEN, INDIA_CHAT_IDS, msg)

# Main Loop
def run():
    while True:
        # ✅ Crypto always on
        for sym in CRYPTO_SYMBOLS:
            for tf in CRYPTO_TIMEFRAMES:
                df = get_crypto_data(sym, tf)
                analyze_data(df, sym, tf, market="crypto")
            if sym in SPECIAL_5M:
                df = get_crypto_data(sym, "5m")
                analyze_data(df, sym, "5m", market="crypto")

        # ✅ Indian market alerts only in market hours
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(tz)
        if now.weekday() < 5 and now.hour >= 9 and (now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
            for sym in INDIAN_SYMBOLS:
                for tf in INDIA_TIMEFRAMES:
                    df = get_indian_data(sym, interval=tf)
                    analyze_data(df, sym, tf, market="india")

        time.sleep(300)  # run every 5 mins

if __name__ == "__main__":
    run()
