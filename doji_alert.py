import pandas as pd
import time
from binance.client import Client
from nsepython import nse_eq, nse_index
import datetime as dt

# Binance client (for crypto)
client = Client()

# Config
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "LTCUSDT"]
INDIAN_INDICES = ["NIFTY 50", "NIFTY BANK", "SENSEX", "BANKEX"]

# Top 20 Indian stocks
INDIAN_TOP20 = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK",
    "SBIN","HINDUNILVR","BHARTIARTL","KOTAKBANK","ITC",
    "LT","ASIANPAINT","BAJFINANCE","MARUTI","AXISBANK",
    "SUNPHARMA","ULTRACEMCO","TITAN","WIPRO","HCLTECH"
]

CRYPTO_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
INDEX_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "4h", "1d", "1w", "1M"]

SEPERATOR = "━━━━━━━━✦✧✦━━━━━━━━"

# ---------------- Crypto fetch ----------------
def fetch_crypto_data(symbol, interval="15m", limit=50):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "time","open","high","low","close","volume","close_time",
            "qav","num_trades","tbbav","tbqav","ignore"
        ])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df.set_index("time", inplace=True)
        df = df.astype(float)
        return df[["open","high","low","close","volume"]]
    except Exception as e:
        print(f"Crypto fetch error {symbol}: {e}")
        return pd.DataFrame()

# ---------------- Indian fetch ----------------
def fetch_indian_data(symbol, interval="15m"):
    try:
        if symbol in INDIAN_INDICES:
            data = nse_index(symbol)
        else:
            data = nse_eq(symbol)

        candles = []
        for row in data.get("grapthData", []):
            ts, price = row
            candles.append({
                "datetime": pd.to_datetime(ts, unit="ms"),
                "open": price,
                "high": price,
                "low": price,
                "close": price
            })
        df = pd.DataFrame(candles).set_index("datetime")
        return df
    except Exception as e:
        print(f"Indian fetch error {symbol}: {e}")
        return pd.DataFrame()

# ---------------- Doji detection ----------------
def is_doji(open_price, close_price, high, low, threshold=0.1):
    body = abs(close_price - open_price)
    rng = high - low if high - low != 0 else 1
    return (body / rng) < threshold

# ---------------- Alert generator ----------------
def check_alerts():
    messages = []

    # Crypto alerts
    for sym in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TFS:
            df = fetch_crypto_data(sym, tf, limit=10)
            if df.empty: continue
            last = df.iloc[-1]
            if is_doji(last["open"], last["close"], last["high"], last["low"]):
                messages.append(f"🔔 Alert 🔔 | {sym} | TF: {tf}") 

    # Special fast alerts for BTC, ETH, SOL (5m)
    for sym in ["BTCUSDT","ETHUSDT","SOLUSDT"]:
        df = fetch_crypto_data(sym, "5m", limit=10)
        if df.empty: continue
        last = df.iloc[-1]
        if is_doji(last["open"], last["close"], last["high"], last["low"]):
            messages.append(f"⚡ FAST 5m Alert | {sym}")

    # Indian Index alerts
    for sym in INDIAN_INDICES:
        for tf in INDEX_TFS:
            df = fetch_indian_data(sym, tf)
            if df.empty: continue
            last = df.iloc[-1]
            if is_doji(last["open"], last["close"], last["high"], last["low"]):
                messages.append(f"🔔 Alert 🔔 | {sym} | TF: {tf}")

    # Indian Top20 stock alerts
    for sym in INDIAN_TOP20:
        for tf in STOCK_TFS:
            df = fetch_indian_data(sym, tf)
            if df.empty: continue
            last = df.iloc[-1]
            if is_doji(last["open"], last["close"], last["high"], last["low"]):
                messages.append(f"🔔 Alert 🔔 | {sym} | TF: {tf}")

    # Batch message format
    if messages:
        final_msg = "\n" + f"\n{SEPERATOR}\n".join(messages)
        prime_msg = f"\n✨ PRIME ALERT ✨\n{final_msg}\n{SEPERATOR}\n"
        print(prime_msg)

# ---------------- Runner ----------------
if __name__ == "__main__":
    while True:
        check_alerts()
        time.sleep(300)  # run every 5 minutes
