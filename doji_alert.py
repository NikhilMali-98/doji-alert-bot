import time
import requests
import pandas as pd
from binance.client import Client
from nsepython import nse_eq, nsefetch
from datetime import datetime, timedelta, timezone

# ================== TELEGRAM CONFIG ==================
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

# ================== SYMBOL SETS ==================
# Crypto (Binance)
CRYPTO_SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "ADAUSDT","DOGEUSDT","MATICUSDT","DOTUSDT","LTCUSDT"
]
CRYPTO_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]

# Indian Indices
# NSE (index names must match NSE's chart endpoint exactly)
NSE_INDICES = {
    "NIFTY 50": "NIFTY 50",
    "NIFTY BANK": "NIFTY BANK",
}
# BSE Index codes for BSE API
BSE_INDICES = {
    "SENSEX": 16,   # BSE SENSEX
    "BANKEX": 108,  # BSE BANKEX
}
INDEX_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]

# Indian Top 20 Stocks (NSE symbols)
INDIAN_TOP20 = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK",
    "SBIN","HINDUNILVR","BHARTIARTL","KOTAKBANK","ITC",
    "LT","ASIANPAINT","BAJFINANCE","MARUTI","AXISBANK",
    "SUNPHARMA","ULTRACEMCO","TITAN","WIPRO","HCLTECH"
]
STOCK_TFS = ["1h", "4h", "1d", "1w", "1M"]

# ================== CONSTANTS ==================
SEPARATOR = "━━━━━━━━✦✧✦━━━━━━━━"
IST = timezone(timedelta(hours=5, minutes=30))
BINANCE = Client()

# de-dup per candle (symbol, tf, direction, candle_close_ts)
alerted = set()

# ================== HELPERS ==================
def ist_now_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")

def in_india_market_hours(now_ist: datetime) -> bool:
    # Mon–Fri, 09:15–15:30 IST
    if now_ist.weekday() >= 5:
        return False
    start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now_ist <= end

def tf_to_pandas(tf: str) -> str:
    return {
        "15m": "15T", "30m": "30T",
        "1h": "1H", "4h": "4H",
        "1d": "1D", "1w": "1W", "1M": "1M"
    }[tf]

def send_telegram(bot_token: str, message: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            requests.post(url, data={"chat_id": chat_id, "text": message})
        except Exception as e:
            print("Telegram Error:", e)

# ================== FETCHERS ==================
# ---- Crypto (Binance OHLC) ----
def fetch_crypto_ohlc(symbol: str, interval: str, limit: int = 10) -> pd.DataFrame:
    try:
        kl = BINANCE.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not kl:
            return pd.DataFrame()
        df = pd.DataFrame(kl, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qav","trades","tbbav","tbqav","ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(IST)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True).dt.tz_convert(IST)
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        df = df[["open_time","open","high","low","close","close_time"]]
        return df
    except Exception as e:
        print(f"Crypto fetch error {symbol} {interval}: {e}")
        return pd.DataFrame()

# ---- NSE Index (chart-databyindex) ----
def fetch_nse_index_close_series(index_display_name: str) -> pd.DataFrame:
    """Returns minute-level close series with 'dt' and 'close' columns (IST tz)."""
    try:
        url = f"https://www.nseindia.com/api/chart-databyindex?index={index_display_name}&indices=true"
        data = nsefetch(url)
        arr = data.get("grapthData", []) or data.get("graphData", [])
        if not arr:
            return pd.DataFrame()
        rows = []
        for ts, price in arr:
            rows.append({
                "dt": pd.to_datetime(ts, unit="ms", utc=True).tz_convert(IST),
                "close": float(price)
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"NSE index fetch error {index_display_name}: {e}")
        return pd.DataFrame()

# ---- BSE Index (public API) ----
def fetch_bse_index_close_series(scripcode: int) -> pd.DataFrame:
    """
    BSE index graph endpoint. Returns series with 'dt','close'.
    scripcode: 16 (SENSEX), 108 (BANKEX)
    """
    try:
        url = f"https://api.bseindia.com/BseIndiaAPI/api/IndexGraph/w?scripcode={scripcode}&flag=0"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json() or []
        rows = []
        for item in data:
            # API fields differ; handle common possibilities
            # Try 'CurrDate' or 'Date' and 'IndexValue' or 'Close'
            dt_str = item.get("CurrDate") or item.get("Date")
            val = item.get("IndexValue") or item.get("Close") or item.get("Value")
            if not dt_str or val is None:
                continue
            # BSE date often like '/Date(1693215600000)/' or '31 Aug 2025 15:29'
            if "Date(" in str(dt_str):
                ms = int(str(dt_str).split("Date(")[1].split(")")[0])
                dt_local = pd.to_datetime(ms, unit="ms", utc=True).tz_convert(IST)
            else:
                dt_local = pd.to_datetime(dt_str).tz_localize(IST) if pd.to_datetime(dt_str).tzinfo is None else pd.to_datetime(dt_str).tz_convert(IST)
            rows.append({"dt": dt_local, "close": float(val)})
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"BSE index fetch error {scripcode}: {e}")
        return pd.DataFrame()

# ---- NSE Stock (chart data) ----
def fetch_nse_stock_close_series(symbol: str) -> pd.DataFrame:
    try:
        data = nse_eq(symbol)
        arr = data.get("grapthData", []) or data.get("graphData", [])
        if not arr:
            return pd.DataFrame()
        rows = []
        for ts, price in arr:
            rows.append({
                "dt": pd.to_datetime(ts, unit="ms", utc=True).tz_convert(IST),
                "close": float(price)
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"NSE stock fetch error {symbol}: {e}")
        return pd.DataFrame()

def resample_close_to_ohlc(df_close: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Make OHLC from close series using resample; returns last ~100 bars."""
    if df_close.empty:
        return pd.DataFrame()
    df = df_close.copy()
    df = df.set_index("dt").sort_index()
    rule = tf_to_pandas(tf)
    ohlc = df["close"].resample(rule, label="right", closed="right").ohlc()
    ohlc = ohlc.dropna()
    ohlc = ohlc.rename(columns={"open":"open", "high":"high", "low":"low", "close":"close"})
    # Keep a reasonable tail
    return ohlc.tail(100).reset_index().rename(columns={"dt":"time"})

# ================== DOJI + BREAKOUT ==================
def is_doji(open_, high, low, close, body_ratio=0.2):
    """
    Strict doji: real body <= 20% of range (default).
    Returns (is_doji, is_prime) where 'prime' is high==low case.
    """
    rng = high - low
    if rng == 0:
        return True, True  # PRIME
    body = abs(close - open_)
    return (body <= body_ratio * rng), False

def detect_two_doji_breakout(df_ohlc: pd.DataFrame):
    """
    Needs at least last 3 bars: c1, c2 (dojis), c3 (breakout close beyond doji bodies).
    Returns tuple (triggered, direction, low, high, last_close, prime)
    """
    if df_ohlc is None or len(df_ohlc) < 3:
        return (False, None, None, None, None, False, None)
    c1 = df_ohlc.iloc[-3]
    c2 = df_ohlc.iloc[-2]
    c3 = df_ohlc.iloc[-1]

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
    candle_ts = c3.get("close_time") or c3.get("time")
    return (True, direction, body_low, body_high, c3["close"], prime, candle_ts)

# ================== MESSAGE BUILDER ==================
def fmt_symbol_market(symbol: str, market: str) -> str:
    if market == "CRYPTO":
        return symbol.replace("USDT", "USD")
    # Indian – keep as is
    return symbol

def make_msg(symbol: str, tf: str, direction: str, low: float, high: float, last_close: float, prime: bool, market: str) -> str:
    ts = ist_now_str()
    sym = fmt_symbol_market(symbol, market)
    rng = f"{round(low,4)}-{round(high,4)}"
    px  = f"{round(last_close,4)}"
    if prime:
        # simple & neat prime header
        head = f"🔥 PRIME ALERT 🔥"
        body = f"{sym} | {tf} | {direction}\nRange: {rng} | Price: {px}\n🕒 {ts} IST"
        return f"{head}\n{body}"
    else:
        return f"🚨 {sym} | {tf} | {direction}\nRange: {rng} | Price: {px}\n🕒 {ts} IST"

# ================== SCANNERS ==================
def scan_crypto() -> list[str]:
    msgs = []
    for sym in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TFS:
            df = fetch_crypto_ohlc(sym, tf, limit=5)
            if df.empty or len(df) < 3:
                continue
            trig, direction, low, high, last_close, prime, candle_ts = detect_two_doji_breakout(df)
            if not trig:
                continue
            # de-dup per (sym, tf, dir, candle_close)
            key = (sym, tf, direction, str(candle_ts))
            if key in alerted:
                continue
            alerted.add(key)
            msgs.append(make_msg(sym, tf, direction, low, high, last_close, prime, "CRYPTO"))
    return msgs

def scan_india() -> list[str]:
    msgs = []
    # Indices (NSE)
    for disp_name in NSE_INDICES.values():
        close_df = fetch_nse_index_close_series(disp_name)
        if close_df.empty:
            continue
        for tf in INDEX_TFS:
            ohlc = resample_close_to_ohlc(close_df, tf)
            if ohlc.empty or len(ohlc) < 3:
                continue
            trig, direction, low, high, last_close, prime, candle_ts = detect_two_doji_breakout(ohlc)
            if not trig:
                continue
            key = (disp_name, tf, direction, str(candle_ts))
            if key in alerted:
                continue
            alerted.add(key)
            msgs.append(make_msg(disp_name, tf, direction, low, high, last_close, prime, "INDIA"))

    # Indices (BSE)
    for name, code in BSE_INDICES.items():
        close_df = fetch_bse_index_close_series(code)
        if close_df.empty:
            continue
        for tf in INDEX_TFS:
            ohlc = resample_close_to_ohlc(close_df, tf)
            if ohlc.empty or len(ohlc) < 3:
                continue
            trig, direction, low, high, last_close, prime, candle_ts = detect_two_doji_breakout(ohlc)
            if not trig:
                continue
            key = (name, tf, direction, str(candle_ts))
            if key in alerted:
                continue
            alerted.add(key)
            msgs.append(make_msg(name, tf, direction, low, high, last_close, prime, "INDIA"))

    # Top 20 stocks (NSE)
    for sym in INDIAN_TOP20:
        close_df = fetch_nse_stock_close_series(sym)
        if close_df.empty:
            continue
        for tf in STOCK_TFS:
            ohlc = resample_close_to_ohlc(close_df, tf)
            if ohlc.empty or len(ohlc) < 3:
                continue
            trig, direction, low, high, last_close, prime, candle_ts = detect_two_doji_breakout(ohlc)
            if not trig:
                continue
            key = (sym, tf, direction, str(candle_ts))
            if key in alerted:
                continue
            alerted.add(key)
            msgs.append(make_msg(sym, tf, direction, low, high, last_close, prime, "INDIA"))

    return msgs

# ================== MAIN LOOP ==================
def main():
    print("🚀 Combined Doji Breakout Bot (Crypto + India) started...")
    while True:
        # Crypto always
        c_msgs = scan_crypto()

        # India only during market hours
        i_msgs = []
        now_ist = datetime.now(IST)
        if in_india_market_hours(now_ist):
            i_msgs = scan_india()

        # Batch + send
        if c_msgs:
            payload = f"\n{SEPARATOR}\n".join(c_msgs)
            send_telegram(CRYPTO_BOT_TOKEN, payload)

        if i_msgs:
            payload = f"\n{SEPARATOR}\n".join(i_msgs)
            send_telegram(INDIA_BOT_TOKEN, payload)

        # small console hint
        print(f"Cycle done | Crypto alerts: {len(c_msgs)} | India alerts: {len(i_msgs)} | {ist_now_str()} IST")

        time.sleep(300)  # run every 5 mins

if __name__ == "__main__":
    main()
