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

# Cooldown per timeframe (seconds); fallback 600s
TF_COOLDOWN_SEC = {
    "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400,
    "1d": 86400, "1w": 604800, "1M": 2592000
}

# ================== SYMBOL SETS ==================
# Crypto (Binance)
CRYPTO_SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "DOGEUSDT","AVAXUSDT","LINKUSDT","ADAUSDT","TRXUSDT"
]
CRYPTO_TFS = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

# Indian Indices (Yahoo tickers)
INDICES_MAP = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"],
    "SENSEX": ["^BSESN"],
    "BSE BANKEX": ["^BSEBANK", "BSE-BANK.BO"],  # fallback
}

# Top 15 Nifty stocks (NSE tickers)
TOP15_STOCKS_NS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "LT.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","HINDUNILVR.NS","ASIANPAINT.NS","MARUTI.NS","BAJFINANCE.NS"
]

INDEX_TFS = ["15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "2h", "4h", "1d", "1w", "1M"]  # stocks साठी 15/30 कमी value; तरी ठेवू शकतो

# ================== CLIENTS & STATE ==================
BINANCE = Client()  # public market data okay without keys
last_alert_at = {}  # key=(mkt,symbol,tf,dir) -> epoch
last_bar_key = set()  # dedup per bar: (mkt,symbol,tf,bar_ts,dir)

# ================== HELPERS ==================
def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def is_india_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

def tf_to_pandas(tf: str) -> str:
    return {
        "5m": "5T", "15m": "15T", "30m": "30T",
        "1h": "1H", "2h": "2H", "4h": "4H",
        "1d": "1D", "1w": "1W", "1M": "1M"
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
def is_doji(open_, high, low, close, price_for_abs=0.0):
    """
    Updated doji rule:
      - range == 0  -> True, prime
      - abs(body) <= 0.5 (absolute) -> True
      - abs(body) <= 1% of range -> True
    Prime:
      - abs(body) <= 0.1% of price  OR range == 0
    """
    body = abs(close - open_)
    rng = high - low
    if rng == 0:
        return True, True
    # doji check
    if body <= 0.5:
        doji = True
    elif body <= 0.01 * rng:
        doji = True
    else:
        doji = False
    # prime check
    mid_price = price_for_abs if price_for_abs > 0 else (high + low) / 2.0
    prime = (body <= 0.001 * mid_price) or (rng == 0)
    return doji, prime

def detect_two_doji_breakout(df_ohlc: pd.DataFrame):
    """
    Needs last 3 bars: c1, c2 (dojis), c3 (breakout close beyond doji bodies).
    Returns (triggered, direction, low, high, last_close, prime, bar_ts)
    """
    if df_ohlc is None or len(df_ohlc) < 3:
        return (False, None, None, None, None, False, None)
    c1 = df_ohlc.iloc[-3]
    c2 = df_ohlc.iloc[-2]
    c3 = df_ohlc.iloc[-1]

    d1, p1 = is_doji(c1["open"], c1["high"], c1["low"], c1["close"], price_for_abs=c1["close"])
    d2, p2 = is_doji(c2["open"], c2["high"], c2["low"], c2["close"], price_for_abs=c2["close"])
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
    # bar_ts for dedup
    bar_ts = c3.get("close_time") or c3.get("time")
    return (True, direction, body_low, body_high, c3["close"], prime, bar_ts)

def make_msg(symbol: str, tf: str, direction: str, low: float, high: float, last_close: float, prime: bool, market: str) -> str:
    ts = ist_now_str()
    # Pretty symbol for crypto
    if market == "CRYPTO":
        sym = symbol.replace("USDT", "USD")
    else:
        sym = symbol
    low_s  = f"{low:.4f}"
    high_s = f"{high:.4f}"
    px_s   = f"{last_close:.4f}"
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

# ================== CRYPTO FETCHERS ==================
def fetch_crypto_ohlc(symbol: str, interval: str, limit: int = 5) -> pd.DataFrame:
    """
    Binance public klines -> DataFrame with columns:
    ['open','high','low','close','close_time']
    """
    try:
        kl = BINANCE.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not kl:
            return pd.DataFrame()
        rows = []
        for c in kl:
            rows.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low":  float(c[3]),
                "close":float(c[4]),
                "close_time": int(c[6])  # ms
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"Crypto fetch error {symbol} {interval}: {e}")
        return pd.DataFrame()

# ================== INDIAN (YF) FETCHERS ==================
def fetch_yf_ohlc(symbol: str, tf: str) -> pd.DataFrame:
    """
    Yahoo 1m intraday -> resample to tf OHLC.
    For 1D/1W/1M, use appropriate resample rule.
    """
    try:
        # try 1m intraday (works only live market hours / last some days)
        t = yf.Ticker(symbol)
        hist = t.history(period="1d", interval="1m", auto_adjust=False)
        if hist.empty:
            # fallback 5m intraday
            hist = t.history(period="5d", interval="5m", auto_adjust=False)
            if hist.empty:
                return pd.DataFrame()

        # normalize
        df = hist[["Open","High","Low","Close"]].copy()
        df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
        # ensure tz to IST
        df.index = pd.to_datetime(df.index).tz_localize(None)
        # localize to UTC naive -> then convert to IST naive index for resample labels
        # (resample itself is wall-clock; keep as naive)
        rule = tf_to_pandas(tf)
        ohlc = df.resample(rule, label="right", closed="right").agg({
            "open":"first","high":"max","low":"min","close":"last"
        }).dropna()
        if ohlc.empty:
            return pd.DataFrame()
        ohlc = ohlc.tail(100).reset_index().rename(columns={"Datetime":"time","Date":"time"})
        return ohlc
    except Exception as e:
        print(f"YF fetch error {symbol} {tf}: {e}")
        return pd.DataFrame()

def first_working_ticker(symbol_aliases: list[str], tf: str) -> tuple[str, pd.DataFrame]:
    for s in symbol_aliases:
        df = fetch_yf_ohlc(s, tf)
        if not df.empty:
            return s, df
    return "", pd.DataFrame()

# ================== SCANNERS ==================
def scan_crypto() -> list[str]:
    msgs = []
    for sym in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TFS:
            df = fetch_crypto_ohlc(sym, tf, limit=5)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig:
                continue
            bar_key = ("CRYPTO", sym, tf, bar_ts, direction)
            if bar_key in last_bar_key:
                continue
            if not cooldown_ok("CRYPTO", sym, tf, direction):
                continue
            last_bar_key.add(bar_key)
            msgs.append(make_msg(sym, tf, direction, low, high, last_close, prime, "CRYPTO"))
    return msgs

def scan_india() -> list[str]:
    msgs = []
    # Indices
    for name, aliases in INDICES_MAP.items():
        for tf in INDEX_TFS:
            alias, df = first_working_ticker(aliases, tf)
            if not alias or df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig:
                continue
            # for yf, bar_ts use last row time
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", name, tf, bar_ts, direction)
            if bar_key in last_bar_key:
                continue
            if not cooldown_ok("INDIA", name, tf, direction):
                continue
            last_bar_key.add(bar_key)
            msgs.append(make_msg(name, tf, direction, low, high, last_close, prime, "INDIA"))

    # Top 15 stocks
    for sym in TOP15_STOCKS_NS:
        disp = sym.replace(".NS", "")
        for tf in STOCK_TFS:
            df = fetch_yf_ohlc(sym, tf)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, bar_ts = detect_two_doji_breakout(df)
            if not trig:
                continue
            bar_ts = str(df.iloc[-1]["time"])
            bar_key = ("INDIA", disp, tf, bar_ts, direction)
            if bar_key in last_bar_key:
                continue
            if not cooldown_ok("INDIA", disp, tf, direction):
                continue
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

        # batch send (separate bots)
        if c_msgs:
            send_telegram(CRYPTO_BOT_TOKEN, c_msgs)
        if i_msgs:
            send_telegram(INDIA_BOT_TOKEN, i_msgs)

        print(f"Cycle done | Crypto: {len(c_msgs)} | India: {len(i_msgs)} | {ist_now_str()} IST")
        time.sleep(300)  # every 5 min

if __name__ == "__main__":
    main()
