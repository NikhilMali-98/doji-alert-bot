import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from binance.client import Client
from apscheduler.schedulers.background import BackgroundScheduler

# API Keys
ALPHA_VANTAGE_KEY = "4BA9H4URO6LTAXY9"
FINNHUB_KEY = "d304v11r01qnmrsd01k0d304v11r01qnmrsd01kg"

# Bot Configuration
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801", "1269772473"]
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BIG_TFS = {"4h", "1d", "1w", "1M"}
TF_COOLDOWN_SEC = {
    "5m": 240, "15m": 720, "30m": 1500,
    "1h": 3300, "2h": 6600, "4h": 13200,
    "1d": 79200, "1w": 561600, "1M": 2505600
}
CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
CRYPTO_TFS = ["15m", "1h", "2h", "4h", "1d", "1w", "1M"]
INDICES_MAP = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"]
}
TOP15_STOCKS_NS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "LT.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","HINDUNILVR.NS","ASIANPAINTS.NS","MARUTI.NS","BAJFINANCE.NS"
]
INDEX_TFS = ["15m", "1h", "2h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "2h", "4h", "1d", "1w", "1M"]

# Initialize Binance Client
BINANCE = Client()

# State tracking
last_alert_at = {}
last_bar_key = set()
alpha_cache = {"last_time": 0, "data": {}}
finnhub_cache = {"last_time": 0, "data": {}}
API_RATE_LIMITS = {
    "ALPHA_VANTAGE": {"max_calls": 5, "window_seconds": 60, "calls": 0, "last_reset": 0},
    "FINNHUB": {"max_calls": 60, "window_seconds": 60, "calls": 0, "last_reset": 0}
}

def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def is_india_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def tf_to_pandas(tf: str) -> str:
    return {
        "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "2h": "2h", "4h": "4h",
        "1d": "1D", "1w": "1W", "1M": "ME"
    }[tf]

def cooldown_ok(market: str, symbol: str, tf: str, direction: str) -> bool:
    key = (market, symbol, tf, direction)
    now = int(datetime.now(IST).timestamp())
    cd = TF_COOLDOWN_SEC.get(tf, 600)
    last = last_alert_at.get(key, 0)
    if now - last >= cd:
        last_alert_at[key] = now
        return True
    return False

def check_api_limit(api_name: str) -> bool:
    limit = API_RATE_LIMITS[api_name]
    now = time.time()
    if now - limit["last_reset"] > limit["window_seconds"]:
        limit["last_reset"] = now
        limit["calls"] = 0
    if limit["calls"] < limit["max_calls"]:
        limit["calls"] += 1
        return True
    print(f"{ist_now_str()} - API limit exceeded for {api_name}")
    return False

def send_telegram(bot_token: str, messages: list[str], image_buf=None):
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

def is_doji(open_, high, low, close, volume=None):
    body = abs(open_ - close)
    rng = high - low
    if rng == 0:
        return True, True
    if body <= 0.02 * rng or body <= 0.00003 * close:
        if volume and volume > 0:
            return True, True
    if body <= 0.20 * rng:
        return True, False
    return False, False

def detect_multi_doji_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 3:
        return False, None, None, None, None, False, None
    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]
    doji_indices = []
    prime_found = False
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        d, p = is_doji(row["open"], row["high"], row["low"], row["close"], row.get("volume"))
        if d:
            doji_indices.append(i)
            if p:
                prime_found = True
        else:
            break
    if len(doji_indices) < 2:
        return False, None, None, None, None, False, None
    doji_candles = candles.iloc[min(doji_indices):]
    body_high = max(doji_candles[["open","close"]].max())
    body_low  = min(doji_candles[["open","close"]].min())
    direction = None
    if breakout_candle["high"] > body_high:
        direction = "UP ✅"
    elif breakout_candle["low"] < body_low:
        direction = "DOWN ✅"
    if not direction:
        return False, None, None, None, None, False, None
    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return True, direction, body_low, body_high, breakout_candle["close"], prime_found, bar_ts

def detect_consolidation_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 4:
        return False, None, None, None, None, None
    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]
    last_3 = candles.iloc[-3:]
    body_ranges = abs(last_3["open"] - last_3["close"])
    total_range = last_3["high"].max() - last_3["low"].min()
    if total_range == 0:
        return False, None, None, None, None, None
    if all(body_ranges <= 0.05 * total_range):
        body_low = last_3["low"].min()
        body_high = last_3["high"].max()
        last_close = breakout_candle["close"]
        bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
        if breakout_candle["high"] > body_high:
            direction = "UP ✅"
            return True, direction, body_low, body_high, last_close, bar_ts
        elif breakout_candle["low"] < body_low:
            direction = "DOWN ✅"
            return True, direction, body_low, body_high, last_close, bar_ts
    return False, None, None, None, None, None

def detect_multi_inside_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 4:
        return False, None, None, None, None, None
    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]
    inside_count = 0
    last_low = breakout_candle["low"]
    last_high = breakout_candle["high"]
    for i in range(len(candles)-1, -1, -1):
        row = candles.iloc[i]
        if row["high"] <= last_high and row["low"] >= last_low:
            inside_count += 1
            last_low = min(last_low, row["low"])
            last_high = max(last_high, row["high"])
        else:
            break
    if inside_count < 2:
        return False, None, None, None, None, None
    direction = None
    if breakout_candle["high"] > last_high:
        direction = "UP ✅"
    elif breakout_candle["low"] < last_low:
        direction = "DOWN ✅"
    if not direction:
        return False, None, None, None, None, None
    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return True, direction, last_low, last_high, breakout_candle["close"], bar_ts

def make_msg(symbol, tf, direction, low, high, last_close, prime, market, special_alert=False):
    ts = ist_now_str()
    sym = symbol.replace("USDT", "USD") if market == "CRYPTO" else symbol
    low_s, high_s, px_s = f"{low:.4f}", f"{high:.4f}", f"{last_close:.4f}"
    header = ""
    if tf in BIG_TFS:
        header += "🔶 BIG TF 🔶\n"
    if special_alert:
        header += "🔥 CONSOLIDATION 🔥\n"
    elif prime:
        header += "🚨 PRIME 🚨\n"
    return (
        f"{header}🚨 {sym} | {tf} | {direction}\n"
        f"Range: {low_s}-{high_s} | Price: {px_s}\n"
        f"🕒 {ts} IST"
    )

def plot_doji_chart(df, symbol, tf, direction, low, high, last_close):
    df = df.tail(10).copy()
    fig, ax = plt.subplots(figsize=(6,4))
    ax.set_title(f"{symbol} {tf} | {direction}", fontsize=10)
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax.plot([i,i],[row["low"], row["high"]], color=color)
        ax.add_patch(plt.Rectangle((i-0.3, min(row["open"], row["close"])),
                                   0.6, abs(row["open"]-row["close"]),
                                   color=color, alpha=0.6))
    # Breakout lines
    ax.axhline(low, color="blue", linestyle="--", label="Range Low")
    ax.axhline(high, color="orange", linestyle="--", label="Range High")
    ax.axhline(last_close, color="black", linestyle=":", label="Last Close")
    ax.legend(fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

# Functions for data fetching, retry, cache, fallback remain same as before...

# ...fetch_crypto_ohlc(), fetch_yf_ohlc(), fetch_fallback_ohlc(), first_working_ticker(), etc.

# Scan functions
def scan_market(market_name, symbols_list, timeframes, bot_token, extra_info=""):
    for symbol in symbols_list:
        for tf in timeframes:
            if market_name == "CRYPTO":
                df = fetch_crypto_ohlc(symbol, tf, limit=8)
            else:
                df = fetch_yf_ohlc(symbol, tf)

            if df.empty or len(df) < 3:
                if market_name == "INDIA":
                    print(f"{ist_now_str()} - Error: No data for {symbol} at {tf}")
                continue

            trig, direction, low, high, last_close, prime, bar_ts = detect_multi_doji_breakout(df)
            if trig:
                bar_key = (market_name, symbol, tf, bar_ts, direction)
                if bar_key not in last_bar_key and cooldown_ok(market_name, symbol, tf, direction):
                    last_bar_key.add(bar_key)
                    msg = make_msg(symbol, tf, direction, low, high, last_close, prime, market_name)
                    chart_buf = plot_doji_chart(df, symbol, tf, direction, low, high, last_close)
                    send_telegram(bot_token, [msg], chart_buf)

            cons, direction, low, high, last_close, bar_ts = detect_consolidation_breakout(df)
            if cons:
                bar_key = (market_name + "_CONS", symbol, tf, bar_ts, direction)
                if bar_key not in last_bar_key and cooldown_ok(market_name, symbol, tf, direction):
                    last_bar_key.add(bar_key)
                    msg = make_msg(symbol, tf, direction, low, high, last_close, False, market_name, special_alert=True)
                    chart_buf = plot_doji_chart(df, symbol, tf, direction, low, high, last_close)
                    send_telegram(bot_token, [msg], chart_buf)

            multi_trig, direction, low, high, last_close, bar_ts = detect_multi_inside_breakout(df)
            if multi_trig:
                bar_key = (market_name + "_INSIDE", symbol, tf, bar_ts, direction)
                if bar_key not in last_bar_key and cooldown_ok(market_name, symbol, tf, direction):
                    last_bar_key.add(bar_key)
                    msg = make_msg(symbol, tf, direction, low, high, last_close, False, market_name, special_alert=True)
                    chart_buf = plot_doji_chart(df, symbol, tf, direction, low, high, last_close)
                    send_telegram(bot_token, [msg], chart_buf)

def scan_crypto():
    print(f"{ist_now_str()} - Scanning crypto market")
    scan_market("CRYPTO", CRYPTO_SYMBOLS, CRYPTO_TFS, CRYPTO_BOT_TOKEN)

def scan_india():
    if not is_india_market_hours():
        print(f"{ist_now_str()} - India market closed. Skipping indices and stocks.")
        return
    for idx_name, aliases in INDICES_MAP.items():
        alias, df = first_working_ticker(aliases, INDEX_TFS[0])
        if alias and not df.empty:
            print(f"{ist_now_str()} - Scanning index {idx_name} ({alias})")
            scan_market("INDIA", [alias], INDEX_TFS, INDIA_BOT_TOKEN, extra_info=f"(Index: {idx_name})")
        else:
            print(f"{ist_now_str()} - Failed to get data for index {idx_name}")
    print(f"{ist_now_str()} - Scanning top stocks")
    scan_market("INDIA", TOP15_STOCKS_NS, STOCK_TFS, INDIA_BOT_TOKEN, extra_info="(Top Stocks)")

def main_loop():
    scheduler = BackgroundScheduler()
    scheduler.add_job(scan_crypto, 'interval', minutes=5)
    scheduler.add_job(scan_india, 'interval', minutes=5)
    scheduler.start()
    print(f"{ist_now_str()} - Scheduler started. Running scans every 5 minutes.")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print(f"{ist_now_str()} - Scheduler stopped.")

if __name__ == "__main__":
    main_loop()
