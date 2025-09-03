import time
import requests
import pandas as pd
import pytz
import yfinance as yf
from datetime import datetime, timedelta, timezone
from binance.client import Client

# ================== TELEGRAM CONFIG ==================
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

# ================== CONSTANTS ==================
SEPARATOR = "━━━━━━━✦✧✦━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BIG_TFS = {"4h", "1d", "1w", "1M"}

TF_COOLDOWN_SEC = {
    "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400,
    "1d": 86400, "1w": 604800, "1M": 2592000
}

# interval map for minutes
MINUTES_MAP = {"m": 1, "h": 60, "d": 1440, "w": 10080, "M": 43200}
def interval_to_minutes(interval: str) -> int:
    try:
        unit = interval[-1]
        val = int(interval[:-1])
        return val * MINUTES_MAP.get(unit, 1)
    except:
        return 5

# ================== SYMBOL SETS ==================
CRYPTO_SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "DOGEUSDT"]
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
        "1d": "1D", "1w": "1W", "1M": "ME"   # M → ME fix
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

def send_telegram(bot_token: str, messages: list[str]):
    if not messages:
        return
    payload = f"\n{SEPARATOR}\n".join(messages)
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": payload})
        except Exception as e:
            print("Telegram Error:", e)

# ================== DOJI + BREAKOUT ==================
def is_doji(open_, high, low, close):
    body = abs(close - open_)
    rng = high - low

    # Special case → perfect doji
    if rng == 0:
        return True, True

    # Normal doji → body ≤ 20% of range
    doji = body <= 0.2 * rng

    # Prime doji stricter → body ≤ 5% of range OR body ≤ 0.05% of close
    prime = (body <= 0.05 * rng) or (body <= 0.0005 * close)

    return doji, prime

def detect_two_doji_breakout(df_ohlc: pd.DataFrame):
    if df_ohlc is None or len(df_ohlc) < 3:
        return (False, None, None, None, None, False, None)
    c1, c2, c3 = df_ohlc.iloc[-3], df_ohlc.iloc[-2], df_ohlc.iloc[-1]

    d1, p1 = is_doji(c1["open"], c1["high"], c1["low"], c1["close"])
    d2, p2 = is_doji(c2["open"], c2["high"], c2["low"], c2["close"])
    if not (d1 and d2):
        return (False, None, None, None, None, False, None)

    body_high = max(c1["open"], c1["close"], c2["open"], c2["close"])
    body_low  = min(c1["open"], c1["close"], c2["open"], c2["close"])

    direction = None
    if c3["close"] > body_high:
        direction = "UP 🚀"
    elif c3["close"] < body_low:
        direction = "DOWN 🔻"
    if not direction:
        return (False, None, None, None, None, False, None)

    prime = (p1 or p2)
    bar_ts = c3.get("close_time") or c3.get("time")
    return (True, direction, body_low, body_high, c3["close"], prime, bar_ts)

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

# ================== FETCHERS ==================
def fetch_crypto_ohlc(symbol, interval, limit=5):
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
            df = fetch_crypto_ohlc(sym, tf, limit=5)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig: continue
            bar_key = ("CRYPTO", sym, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("CRYPTO", sym, tf, direction): continue
            last_bar_key.add(bar_key)
            msgs.append(make_msg(sym, tf, direction, low, high, last_close, prime, "CRYPTO"))
    return msgs

def scan_india():
    msgs = []
    for name, aliases in INDICES_MAP.items():
        for tf in INDEX_TFS:
            alias, df = first_working_ticker(aliases, tf)
            if not alias or df.empty or len(df) < 3: continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig: continue
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", name, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("INDIA", name, tf, direction): continue
            last_bar_key.add(bar_key)
            msgs.append(make_msg(name, tf, direction, low, high, last_close, prime, "INDIA"))
    for sym in TOP15_STOCKS_NS:
        disp = sym.replace(".NS", "")
        for tf in STOCK_TFS:
            df = fetch_yf_ohlc(sym, tf)
            if df.empty or len(df) < 3: continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig: continue
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", disp, tf, bar_ts, direction)
            if bar_key in last_bar_key: continue
            if not cooldown_ok("INDIA", disp, tf, direction): continue
            last_bar_key.add(bar_key)
            msgs.append(make_msg(disp, tf, direction, low, high, last_close, prime, "INDIA"))
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
        if c_msgs: send_telegram(CRYPTO_BOT_TOKEN, c_msgs)
        if i_msgs: send_telegram(INDIA_BOT_TOKEN, i_msgs)
        print(f"Cycle done | Crypto: {len(c_msgs)} | India: {len(i_msgs)} | {ist_now_str()} IST")
        time.sleep(300)

if __name__ == "__main__":
    main()
