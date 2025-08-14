import os
import requests
import feedparser
from flask import Flask, request, jsonify
from urllib.parse import quote

# Configuración de variables de entorno (se ponen en Render → Environment)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ACCESS_KEY = os.getenv("ACCESS_KEY")  # Opcional

# Activos de Yahoo Finance
ASSETS = {
    "S&P 500": "^GSPC",
    "ETF Emergentes IMI": "EIMI.L",
    "Oro spot": "XAUUSD=X",
    "Bitcoin": "BTC-USD"
}

# Feeds de noticias
NEWS_FEEDS = [
    "https://feeds.reuters.com/reuters/marketsNews",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://e00-expansion.uecdn.es/rss/mercados.xml"
]

app = Flask(__name__)

def fetch_yahoo_quotes(symbols):
    quotes = {}
    for name, symbol in symbols.items():
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote(symbol)}"
        r = requests.get(url, timeout=10)
        data = r.json()
        try:
            price = data["quoteResponse"]["result"][0]["regularMarketPrice"]
            quotes[name] = price
        except (IndexError, KeyError):
            quotes[name] = "Error"
    return quotes

def fetch_news(feeds):
    news_list = []
    for feed in feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:3]:  # Solo las 3 últimas noticias de cada feed
            news_list.append(f"📰 {entry.title} - {entry.link}")
    return news_list

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    requests.post(url, data=payload)

@app.route("/")
def home():
    return "Bot de bolsa funcionando."

@app.route("/send", methods=["GET"])
def send_update():
    if ACCESS_KEY and request.args.get("key") != ACCESS_KEY:
        return jsonify({"error": "No autorizado"}), 403

    quotes = fetch_yahoo_quotes(ASSETS)
    news = fetch_news(NEWS_FEEDS)

    message = "📊 <b>Actualización de mercados</b>\n\n"
    for name, price in quotes.items():
        message += f"{name}: {price}\n"

    message += "\n<b>Últimas noticias</b>:\n"
    for n in news:
        message += f"{n}\n"

    send_telegram_message(message)
    return jsonify({"status": "ok", "message_sent": message})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
