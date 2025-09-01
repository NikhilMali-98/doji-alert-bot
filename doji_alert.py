import requests
import datetime
import pytz
import ccxt
from nsepython import nse_fno, nse_index, nse_eq

# ================= CONFIG =================
CRYPTO_BOT_TOKEN = "7604294147:AAHRyGR2MX0_wNuQUIr1_QlIrAFc34bxuz8"
INDIA_BOT_TOKEN  = "8462939843:AAEvcFCJKaZqTawZKwPyidvDoy4kFO1j6So"
CHAT_IDS = ["1343842801"]

SEPARATOR = "━━━━━✦✧✦━━━━━"

CRYPTO_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
                  "XRP/USDT", "DOGE/USDT",
                  "DOT/USDT"]

CRYPTO_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
INDEX_TFS = ["15m", "30m", "1h", "4h", "1d", "1w", "1M"]
STOCK_TFS = ["1h", "4h", "1d", "1w", "1M"]

INDIAN_INDICES = {
    "NIFTY50": "nifty 50",
    "BANKNIFTY": "nifty bank",
    "SENSEX": "S&P BSE SENSEX",
    "BANKEX": "S&P BSE BANKEX"
}

TOP20_STOCKS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "KOTAKBANK", "SBIN", "LT", "HINDUNILVR", "BHARTIARTL",
    "ITC", "AXISBANK", "ASIANPAINT", "MARUTI", "BAJFINANCE",
    "HCLTECH", "WIPRO", "SUNPHARMA", "TITAN", "POWERGRID"
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
                prime = body_size <= (0.001 * price)  # body <=0.1% of price → doji
                alerts.append(format_message(symbol.replace("/", ""), tf, direction, low, high, price, prime))
            except Exception as e:
                print(f"Crypto error {symbol} {tf}: {e}")
    if alerts:
        send_telegram_message(CRYPTO_BOT_TOKEN, CHAT_IDS, "\n".join(alerts))

def check_indian_alerts():
    alerts = []
    # 🔹 Indices
    for name, index_code in INDIAN_INDICES.items():
        try:
            data = nse_index(index_code)
            price = data["lastPrice"]
            low, high = data["dayLow"], data["dayHigh"]
            open_price = data["open"]
            close_price = price
            direction = "UP" if price > (low + high) / 2 else "DOWN"
            body_size = abs(close_price - open_price)
            prime = body_size <= (0.001 * price)
            for tf in INDEX_TFS:
                alerts.append(format_message(name, tf, direction, low, high, price, prime))
        except Exception as e:
            print(f"Index error {name}: {e}")

    # 🔹 Stocks
    for stock in TOP20_STOCKS:
        try:
            data = nse_eq(stock)
            price = data["priceInfo"]["lastPrice"]
            low, high = data["priceInfo"]["intraDayLow"], data["priceInfo"]["intraDayHigh"]
            open_price = data["priceInfo"]["open"]
            close_price = price
            direction = "UP" if price > (low + high) / 2 else "DOWN"
            body_size = abs(close_price - open_price)
            prime = body_size <= (0.001 * price)
            for tf in STOCK_TFS:
                alerts.append(format_message(stock, tf, direction, low, high, price, prime))
        except Exception as e:
            print(f"Stock error {stock}: {e}")

    if alerts:
        send_telegram_message(INDIA_BOT_TOKEN, CHAT_IDS, "\n".join(alerts))

# ================= RUN =================
if __name__ == "__main__":
    check_crypto_alerts()
    check_indian_alerts()
