import time
import requests
import pandas as pd
import pytz
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from binance.client import Client
import io

# ================== TELEGRAM CONFIG ==================
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

# ================== CONSTANTS ==================
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BIG_TFS = {"4h", "1d", "1w", "1M"}

TF_COOLDOWN_SEC = {
    "5m": 240, "15m": 720, "30m": 1500,
    "1h": 3300, "2h": 6600, "4h": 13200,
    "1d": 79200, "1w": 561600, "1M": 2505600
}

# ================== SYMBOL SETS ==================
CRYPTO_SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "DOGEUSDT"
]
CRYPTO_TFS = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

INDICES_MAP = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"],
    "SENSEX": ["^BSESN"]
}

TOP15_STOCKS_NS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "LT.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","HINDUNILVR.NS","ASIANPAINT.NS","MARUTI.NS","BAJFINANCE.NS"
]

INDEX_TFS = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "2h", "4h", "1d", "1w", "1M"]

# ================== CLIENTS & STATE ==================
BINANCE = Client()
last_alert_at = {}
last_bar_key = set()

# ================== HELPERS ==================
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

def send_telegram(bot_token: str, messages: list[str], image_buf=None):
    """Send text + optional image to telegram"""
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
            print("Telegram Error:", e)

# ================== DOJI + BREAKOUT ==================
def is_doji(open_, high, low, close):
    body = abs(open_ - close)
    rng = high - low

    if rng == 0:
        return True, True  # special case -> prime

    if body <= 0.05 * rng or body <= 0.0005 * close:
        return True, True  # Prime

    if body <= 0.20 * rng:
        return True, False  # Normal

    return False, False

def detect_multi_doji_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 3:
        return (False, None, None, None, None, False, None)

    candles = df_ohlc.iloc[:-1]
    breakout_candle = df_ohlc.iloc[-1]

    doji_indices = []
    prime_found = False
    for i in range(len(candles)-1, -1, -1):
        d, p = is_doji(candles.iloc[i]["open"], candles.iloc[i]["high"], candles.iloc[i]["low"], candles.iloc[i]["close"])
        if d:
            doji_indices.append(i)
            if p:
                prime_found = True
        else:
            break

    if len(doji_indices) < 2:
        return (False, None, None, None, None, False, None)

    doji_candles = candles.iloc[min(doji_indices):]
    body_high = max(doji_candles[["open","close"]].max())
    body_low  = min(doji_candles[["open","close"]].min())

    direction = None
    if breakout_candle["close"] > body_high:
        direction = "UP 🚀"
    elif breakout_candle["close"] < body_low:
        direction = "DOWN 🔻"
    if not direction:
        return (False, None, None, None, None, False, None)

    bar_ts = breakout_candle.get("close_time") or breakout_candle.get("time")
    return (True, direction, body_low, body_high, breakout_candle["close"], prime_found, bar_ts)

def make_msg(symbol, tf, direction, low, high, last_close, prime, market):
    ts = ist_now_str()
    sym = symbol.replace("USDT", "USD") if market == "CRYPTO" else symbol
    low_s, high_s, px_s = f"{low:.4f}", f"{high:.4f}", f"{last_close:.4f}"
    header = ""
    if tf in BIG_TFS:
        header += "🔶 BIG TF\n"
    if prime:
        header += "🔥 PRIME ALERT 🔥\n"
    return (
        f"{header}🚨 {sym} | {tf} | {direction}\n"
        f"Range: {low_s}-{high_s} | Price: {px_s}\n"
        f"🕒 {ts} IST"
    )

# ================== PLOTTER ==================
def plot_doji_chart(df, symbol, tf, direction, low, high, last_close):
    df = df.tail(10).copy()
    fig, ax = plt.subplots(figsize=(6,4))

    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax.plot([i,i],[row["low"], row["high"]], color=color)
        ax.add_patch(plt.Rectangle((i-0.3, min(row["open"], row["close"])),
                                   0.6, abs(row["open"]-row["close"]),
                                   color=color, alpha=0.6))

    # breakout zone
    ax.axhline(low, color="blue", linestyle="--", label="Doji Zone Low")
    ax.axhline(high, color="orange", linestyle="--", label="Doji Zone High")
    ax.axhline(last_close, color="black", linestyle=":", label="Last Close")

    ax.set_title(f"{symbol} {tf} | {direction}")
    ax.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

# ================== FETCHERS ==================
def fetch_crypto_ohlc(symbol, interval, limit=6):
    try:
        kl = BINANCE.get_klines(symbol=symbol, interval=interval, limit=limit)
        rows = [{
            "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]),
            "close_time": int(c[6])
        } for c in kl]
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"Crypto fetch error {symbol} {interval}: {e}")
        return pd.DataFrame()

def fetch_yf_ohlc(symbol, tf):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1d", interval="1m")
        if hist.empty:
            hist = t.history(period="5d", interval="5m")
        if hist.empty:
            hist = t.history(period="1mo", interval="1d")
        if hist.empty:
            return pd.DataFrame()
        df = hist[["Open","High","Low","Close"]].rename(
            columns={"Open":"open","High":"high","Low":"low","Close":"close"}
        )
        df.index = pd.to_datetime(df.index).tz_localize(None)
        rule = tf_to_pandas(tf)
        ohlc = df.resample(rule, label="right", closed="right").agg(
            {"open":"first","high":"max","low":"min","close":"last"}
        ).dropna()
        return ohlc.tail(100).reset_index().rename(columns={"Datetime":"time","Date":"time"})
    except Exception as e:
        print(f"YF fetch error {symbol} {tf}: {e}")
        return pd.DataFrame()

def first_working_ticker(symbol_aliases, tf):
    for s in symbol_aliases:
        df = fetch_yf_ohlc(s, tf)
        if not df.empty:
            return s, df
    return "", pd.DataFrame()

# ================== SCANNERS ==================
def scan_crypto():
    msgs = []
    for sym in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TFS:
            df = fetch_crypto_ohlc(sym, tf, limit=8)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_multi_doji_breakout(df)
            if not trig: continue
            bar_key = ("CRYPTO", sym, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("CRYPTO", sym, tf, direction): continue
            last_bar_key.add(bar_key)
            msg = make_msg(sym, tf, direction, low, high, last_close, prime, "CRYPTO")
            chart_buf = plot_doji_chart(df, sym, tf, direction, low, high, last_close)
            send_telegram(CRYPTO_BOT_TOKEN, [msg], chart_buf)
            msgs.append(msg)
    return msgs

def scan_india():
    msgs = []
    for name, aliases in INDICES_MAP.items():
        for tf in INDEX_TFS:
            alias, df = first_working_ticker(aliases, tf)
            if not alias or df.empty or len(df) < 3: continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_multi_doji_breakout(df)
            if not trig: continue
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", name, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("INDIA", name, tf, direction): continue
            last_bar_key.add(bar_key)
            msg = make_msg(name, tf, direction, low, high, last_close, prime, "INDIA")
            chart_buf = plot_doji_chart(df, name, tf, direction, low, high, last_close)
            send_telegram(INDIA_BOT_TOKEN, [msg], chart_buf)
            msgs.append(msg)
    for sym in TOP15_STOCKS_NS:
        disp = sym.replace(".NS", "")
        for tf in STOCK_TFS:
            df = fetch_yf_ohlc(sym, tf)
            if df.empty or len(df) < 3: continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_multi_doji_breakout(df)
            if not trig: continue
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", disp, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("INDIA", disp, tf, direction): continue
            last_bar_key.add(bar_key)
            msg = make_msg(disp, tf, direction, low, high, last_close, prime, "INDIA")
            chart_buf = plot_doji_chart(df, disp, tf, direction, low, high, last_close)
            send_telegram(INDIA_BOT_TOKEN, [msg], chart_buf)
            msgs.append(msg)
    return msgs

# ================== MAIN LOOP ==================
def main():
    print("🚀 Combined Doji Breakout Bot (Crypto + India) started...")
    send_telegram(CRYPTO_BOT_TOKEN, ["✅ Crypto scanner online"])
    send_telegram(INDIA_BOT_TOKEN,  ["✅ India scanner online (yfinance best-effort)"])
    while True:
        try:
            c_msgs = scan_crypto()
        except Exception as e:
            print("Crypto scan error:", e)
            c_msgs = []
        i_msgs = []
        try:
            if is_india_market_hours():
                i_msgs = scan_india()
            else:
                print("India market closed, skipping scan.")
        except Exception as e:
            print("India scan error:", e)
        print(f"Cycle done | Crypto: {len(c_msgs)} | India: {len(i_msgs)} | {ist_now_str()} IST")
        time.sleep(300)

if __name__ == "__main__":
    main()
