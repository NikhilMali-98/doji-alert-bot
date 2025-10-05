import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import io

# Bot Configuration
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801", "1269772473"]
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BIG_TFS = {"4h", "1d", "1w", "1M"}
TF_COOLDOWN_SEC = {
    "15m": 720, "1h": 3300, "2h": 6600, "4h": 13200,
    "1d": 79200, "1w": 561600, "1M": 2505600
}
CRYPTO_SYMBOLS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "dogecoin"]
CRYPTO_TFS = ["1d", "7d", "30d"]
INDICES_MAP = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"]
}
TOP15_STOCKS_NS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "LT.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","HINDUNILVR.NS","ASIANPAINTS.NS","MARUTI.NS","BAJFINANCE.NS"
]
INDEX_TFS = ["1d", "1w"]
STOCK_TFS = ["1d", "1w"]

last_alert_at = {}
last_bar_key = set()

def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def is_india_market_hours():
    now = datetime.now(IST)
    return now.weekday() < 5 and now.hour >= 9 and now.hour < 15

def cooldown_ok(market, symbol, tf, direction):
    key = (market, symbol, tf, direction)
    now = int(datetime.now(IST).timestamp())
    cd = TF_COOLDOWN_SEC.get(tf, 600)
    last = last_alert_at.get(key, 0)
    if now - last >= cd:
        last_alert_at[key] = now
        return True
    return False

def send_telegram(bot_token, messages, image_buf=None):
    if not messages:
        return
    payload = f"\n{SEPARATOR}\n".join(messages)
    for chat_id in CHAT_IDS:
        try:
            if image_buf:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                files = {"photo": ("chart.png", image_buf.getvalue())}
                data = {"chat_id": chat_id, "caption": payload}
                requests.post(url, data=data, files=files)
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(url, json={"chat_id": chat_id, "text": payload})
        except Exception as e:
            print(f"{ist_now_str()} - Telegram error: {e}")

def is_doji(open_, high, low, close):
    body = abs(open_ - close)
    rng = high - low
    return rng != 0 and body <= 0.2 * rng

def detect_multi_doji_breakout(df):
    if df is None or len(df) < 3:
        return False, None, None, None, None, None
    candles = df.iloc[:-1]
    breakout = df.iloc[-1]
    dojis = candles[candles.apply(lambda x: is_doji(x["open"], x["high"], x["low"], x["close"]), axis=1)]
    if len(dojis) < 2:
        return False, None, None, None, None, None
    body_high = max(dojis[["open","close"]].max())
    body_low = min(dojis[["open","close"]].min())
    direction = "UP ✅" if breakout["high"] > body_high else "DOWN ✅" if breakout["low"] < body_low else None
    return bool(direction), direction, body_low, body_high, breakout["close"], breakout["time"]

def make_msg(symbol, tf, direction, low, high, last_close, market):
    ts = ist_now_str()
    return (
        f"🚨 {symbol.upper()} | {tf} | {direction}\n"
        f"Range: {low:.2f}-{high:.2f} | Price: {last_close:.2f}\n"
        f"🕒 {ts} IST"
    )

def plot_chart(df, symbol, tf, direction, low, high, last_close):
    df = df.tail(10).copy()
    fig, ax = plt.subplots(figsize=(6,4))
    ax.set_title(f"{symbol} {tf} | {direction}", fontsize=10)
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax.plot([i,i],[row["low"], row["high"]], color=color)
        ax.add_patch(plt.Rectangle((i-0.3, min(row["open"], row["close"])),
                                   0.6, abs(row["open"]-row["close"]),
                                   color=color, alpha=0.6))
    ax.axhline(low, color="blue", linestyle="--")
    ax.axhline(high, color="orange", linestyle="--")
    ax.axhline(last_close, color="black", linestyle=":")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

def fetch_crypto_ohlc(symbol, tf):
    days = {"1d": 1, "7d": 7, "30d": 30}.get(tf, 1)
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency=usd&days={days}"
    try:
        res = requests.get(url)
        data = res.json()
        df = pd.DataFrame(data, columns=["time","open","high","low","close"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except Exception as e:
        print(f"{ist_now_str()} - CoinGecko error for {symbol}: {e}")
        return pd.DataFrame()

def fetch_yf_ohlc(symbol, tf):
    try:
        df = yf.download(symbol, period="30d", interval="1d", progress=False)
        df = df.rename(columns=str.lower)
        df["time"] = df.index
        return df[["open","high","low","close","time"]]
    except:
        return pd.DataFrame()

def scan_market(market, symbols, tfs, bot_token):
    for symbol in symbols:
        for tf in tfs:
            df = fetch_crypto_ohlc(symbol, tf) if market == "CRYPTO" else fetch_yf_ohlc(symbol, tf)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, bar_ts = detect_multi_doji_breakout(df)
            if trig and cooldown_ok(market, symbol, tf, direction):
                msg = make_msg(symbol, tf, direction, low, high, last_close, market)
                chart_buf = plot_chart(df, symbol, tf, direction, low, high, last_close)
                send_telegram(bot_token, [msg], chart_buf)

def scan_crypto():
    print(f"{ist_now_str()} - Scanning crypto market")
    scan_market("CRYPTO", CRYPTO_SYMBOLS, CRYPTO_TFS, CRYPTO_BOT_TOKEN)

def scan_india():
    if not is_india_market_hours():
        print(f"{ist_now_str()} - India market closed.")
        return
    for idx_name, aliases in INDICES_MAP.items():
        scan_market("INDIA_INDEX", aliases, INDEX_TFS, INDIA_BOT_TOKEN)
    scan_market("INDIA_STOCKS", TOP15_STOCKS_NS, STOCK_TFS, INDIA_BOT_TOKEN)

if __name__ == "__main__":
    print("Starting bot...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(scan_crypto, 'interval', minutes=5)
    scheduler.add_job(scan_india, 'interval', minutes=5)
    scheduler.start()
    print("Scheduler
