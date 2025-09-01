import requests
import datetime
import pytz
import ccxt
import yfinance as yf
from nsepython import nse_index, nse_eq

# ================= CONFIG =================
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

SEPARATOR = "━━━━━✦✧✦━━━━━"

CRYPTO_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
                  "XRP/USDT", "DOGE/USDT", "DOT/USDT"]

CRYPTO_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
INDEX_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "4h", "1d", "1w", "1M"]

INDIAN_INDICES = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "BANKEX": "BSE-BANK"
}

TOP20_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "SBIN.NS", "LT.NS", "HINDUNILVR.NS", "BHARTIARTL.NS",
    "ITC.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "HCLTECH.NS", "WIPRO.NS", "SUNPHARMA.NS", "TITAN.NS", "POWERGRID.NS"
]

BIG_TFS = ["4h", "1d", "1w", "1M"]

# ================= UTILS =================
binance = ccxt.binance()

def send_telegram_message(bot_token, chat_ids, message):
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print(f"Error sending message: {e}")

def get_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M IST")

def format_message(symbol, tf, direction, low, high, price, prime=False):
    now = get_time()
    if prime:
        header = "🌟 PRIME ALERT 🌟\n"
    elif tf in BIG_TFS:
        header = "🔥 BIG TF 🔥\n"
    else:
        header = "🚨 ALERT 🚨\n"
    msg = (f"{header}"
           f"{symbol} | {tf} | {direction}\n"
           f"Range: {low}-{high} | Price: {price}\n"
           f"🕒 {now}\n{SEPARATOR}")
    return msg

# ================= ALERT CHECKERS =================
def check_crypto_alerts():
    alerts = []
    for symbol in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TFS:
            try:
                ohlcv = binance.fetch_ohlcv(symbol, tf, limit=2)
                open_price, high, low, close = ohlcv[-1][1], ohlcv[-1][2], ohlcv[-1][3], ohlcv[-1][4]
                price = close
                direction = "UP" if price > (low + high) / 2 else "DOWN"
                body_size = abs(close - open_price)
                prime = body_size <= (0.001 * price)
                alerts.append(format_message(symbol.replace("/", ""), tf, direction, low, high, price, prime))
            except Exception as e:
                print(f"Crypto error {symbol} {tf}: {e}")
    if alerts:
        send_telegram_message(CRYPTO_BOT_TOKEN, CHAT_IDS, "\n".join(alerts))

def get_stock_data_yf(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="1m")
    if hist.empty:
        return None
    latest = hist.iloc[-1]
    open_price = latest["Open"]
    high = latest["High"]
    low = latest["Low"]
    close = latest["Close"]
    return open_price, high, low, close

def check_indian_alerts():
    alerts = []

    # 🔹 Stocks
    for stock in TOP20_STOCKS:
        try:
            data = get_stock_data_yf(stock)
            if not data:
                continue
            open_price, high, low, price = data
            direction = "UP" if price > (low + high) / 2 else "DOWN"
            body_size = abs(price - open_price)
            prime = body_size <= (0.001 * price)
            for tf in STOCK_TFS:
                alerts.append(format_message(stock, tf, direction, low, high, price, prime))
        except Exception as e:
            print(f"Stock error {stock}: {e}")

    # 🔹 Indices
    for name, ticker in INDIAN_INDICES.items():
        try:
            data = get_stock_data_yf(ticker)
            if not data:
                continue
            open_price, high, low, price = data
            direction = "UP" if price > (low + high) / 2 else "DOWN"
            body_size = abs(price - open_price)
            prime = body_size <= (0.001 * price)
            for tf in INDEX_TFS:
                alerts.append(format_message(name, tf, direction, low, high, price, prime))
        except Exception as e:
            print(f"Index error {name}: {e}")

    if alerts:
        send_telegram_message(INDIA_BOT_TOKEN, CHAT_IDS, "\n".join(alerts))

# ================= RUN =================
if __name__ == "__main__":
    check_crypto_alerts()
    check_indian_alerts()
