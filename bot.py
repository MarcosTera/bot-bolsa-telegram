import os, requests, datetime, pytz, math
from flask import Flask, request, jsonify
import feedparser
from urllib.parse import quote

# === Config ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")        # Pónlo en Render > Environment
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")    # Pónlo en Render > Environment
ACCESS_KEY = os.getenv("ACCESS_KEY", "")            # Opcional para proteger el endpoint

# Yahoo Finance symbols (fáciles y líquidos)
ASSETS = {
    "S&P 500": "^GSPC",            # Índice S&P 500
    "MSCI EM IMI (EIMI.L)": "EIMI.L",  # ETF emergentes IMI
    "Oro spot (XAUUSD)": "XAUUSD=X",
    "Bitcoin (BTC-USD)": "BTC-USD",
}

NEWS_FEEDS = [
    "https://feeds.reuters.com/reuters/markets",          # Reuters Markets
    "https://feeds.reuters.com/reuters/businessNews",     # Reuters Business
    "https://e00-expansion.uecdn.es/rss/mercados.xml",    # Expansión Mercados (ES)
]

app = Flask(__name__)

def fetch_yahoo_quotes(symbols):
    url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + quote(",".join(symbols))
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    j = r.json()
    out = {}
    for item in j.get("quoteResponse", {}).get("result", []):
        sym = item.get("symbol")
        out[sym] = {
            "price": item.get("regularMarketPrice"),
            "change": item.get("regularMarketChange"),
            "change_pct": item.get("regularMarketChangePercent"),
            "currency": item.get("currency") or "",
        }
    return out

def format_number(x):
    if x is None:
        return "n/d"
    if isinstance(x, (int, float)):
        # miles con coma y 2 decimales
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(x)

def arrow(pct):
    if pct is None: return "→"
    if pct > 0.05:  return "↑"
    if pct < -0.05: return "↓"
    return "→"

def build_comment(changes):
    sp = changes.get("S&P 500", 0.0) or 0.0
    em = changes.get("MSCI EM IMI (EIMI.L)", 0.0) or 0.0
    au = changes.get("Oro spot (XAUUSD)", 0.0) or 0.0
    btc = changes.get("Bitcoin (BTC-USD)", 0.0) or 0.0

    msgs = []
    # Riesgo vs cobertura
    if sp > 0 and em > 0:
        msgs.append("Sesgo positivo en renta variable, con apoyo de desarrollados y emergentes.")
    elif sp >= 0 and em < 0:
        msgs.append("Desarrollados aguantan mejor que emergentes; divergencia a vigilar.")
    elif sp < 0 and em >= 0:
        msgs.append("Emergentes resisten mientras desarrollados corrigen.")
    else:
        msgs.append("Tono mixto-negativo en bolsa global.")

    if au > 0.2:
        msgs.append("El oro actúa como cobertura con tono alcista.")
    elif au < -0.2:
        msgs.append("El oro cede terreno, menor demanda defensiva.")
    else:
        msgs.append("El oro permanece estable.")

    if abs(btc) >= 1:
        msgs.append("Bitcoin muestra un movimiento notable; volatilidad cripto presente.")
    else:
        msgs.append("Bitcoin sin cambios relevantes.")

    return " ".join(msgs)

def fetch_news(feeds, limit=5):
    titles = []
    for f in feeds:
        try:
            d = feedparser.parse(f)
            for e in d.entries[:limit]:
                t = (e.title or "").strip().replace("\n", " ")
                if t and t not in titles:
                    titles.append(t)
        except Exception:
            pass
        if len(titles) >= limit:
            break
    return titles[:limit]

def compose_report():
    # Fecha local España
    tz = pytz.timezone("Europe/Madrid")
    today = datetime.datetime.now(tz).strftime("%d/%m/%Y")

    # 1) Datos de mercado
    quotes = fetch_yahoo_quotes(list(ASSETS.values()))

    lines = [f"📈 *Informe diario – {today}*"]
    changes = {}

    for name, sym in ASSETS.items():
        q = quotes.get(sym, {})
        price = q.get("price")
        chg_pct = q.get("change_pct")
        curr = q.get("currency", "")
        changes[name] = chg_pct

        arr = arrow(chg_pct)
        price_s = format_number(price)
        pct_s = "n/d" if chg_pct is None else f"{chg_pct:+.2f}%"
        curr_s = curr or ("USD" if "BTC" in name or "Oro" in name else "")
        lines.append(f"*{name}*: {price_s} {curr_s} ({pct_s}) {arr}")

    # 2) Noticias
    news = fetch_news(NEWS_FEEDS, limit=5)
    if news:
        lines.append("\n📰 *Noticias destacadas*")
        for t in news:
            # Evitar caracteres que rompen Markdown
            t = t.replace("*", "·").replace("_", " ").replace("[", "(").replace("]", ")")
            lines.append(f"• {t}")

    # 3) Comentario
    comment = build_comment(changes)
    lines.append(f"\n💡 *Comentario*: {comment}")

    return "\n".join(lines)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en variables de entorno.")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

@app.get("/")
def root():
    return jsonify({"ok": True, "msg": "Informe bolsa bot – use /run para enviar el informe"})

@app.get("/run")
def run():
    # Protección opcional con ?k=TU_CLAVE
    k = request.args.get("k", "")
    if ACCESS_KEY and k != ACCESS_KEY:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        text = compose_report()
        res = send_telegram(text)
        return jsonify({"ok": True, "telegram": res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
