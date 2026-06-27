#!/usr/bin/env python3
"""Sentinella: confronta i prezzi di mercato con la watchlist e invia alert Telegram.

Nessun LLM, nessuna dipendenza esterna: usa solo la libreria standard di Python.
Gira ogni ~5 minuti tramite GitHub Actions (.github/workflows/sentinel.yml).
"""
import json
import os
import time
import urllib.request
import urllib.parse
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WATCHLIST = ROOT / "state" / "watchlist.json"
FIRED = ROOT / "state" / "fired.json"

FINNHUB_KEY = os.environ.get("MARKET_DATA_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def price_finnhub(symbol):
    """Prezzo azioni USA / forex via Finnhub (richiede MARKET_DATA_API_KEY)."""
    if not FINNHUB_KEY:
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(symbol)}&token={FINNHUB_KEY}"
    d = http_get_json(url)
    return float(d["c"]) if d.get("c") else None


def price_coingecko(cg_id):
    """Prezzo crypto via CoinGecko (gratis, senza chiave)."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
    d = http_get_json(url)
    v = d.get(cg_id, {}).get("usd")
    return float(v) if v else None


def get_price(item):
    if item.get("asset_class") == "crypto":
        return price_coingecko(item.get("cg_id") or item["symbol"].lower())
    return price_finnhub(item["symbol"])


def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        print("Telegram non configurato: salto invio.")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"}
    ).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20).read()


def evaluate(item, price):
    """Restituisce la lista di segnali (chiave, messaggio) scattati per questo strumento."""
    sigs = []
    sym = item["symbol"]
    direction = item.get("direction", "long")
    ez = item.get("entry_zone")
    if ez:
        lo, hi = min(ez), max(ez)
        in_zone = (price <= hi) if direction == "long" else (price >= lo)
        if in_zone:
            sigs.append((f"{sym}:ENTRY",
                         f"\U0001F7E2 *ENTRY* {sym}: ${price:.2f} in zona ingresso {lo}-{hi}. {item.get('note', '')}"))
    stop = item.get("stop")
    if stop is not None:
        hit = (price <= stop) if direction == "long" else (price >= stop)
        if hit:
            sigs.append((f"{sym}:STOP", f"\U0001F534 *STOP* {sym}: ${price:.2f} ha toccato lo stop {stop}."))
    for i, t in enumerate(item.get("targets", []), start=1):
        hit = (price >= t) if direction == "long" else (price <= t)
        if hit:
            sigs.append((f"{sym}:TARGET{i}", f"\U0001F3AF *TARGET {i}* {sym}: ${price:.2f} ha raggiunto {t}."))
    return sigs


def main():
    wl = json.loads(WATCHLIST.read_text()) if WATCHLIST.exists() else {"items": []}
    fired = json.loads(FIRED.read_text()) if FIRED.exists() else {}

    # Reset degli alert già inviati quando l'Analista pubblica una nuova watchlist
    if fired.get("_watchlist_stamp") != wl.get("updated_at", ""):
        fired = {"_watchlist_stamp": wl.get("updated_at", "")}

    changed = False
    for item in wl.get("items", []):
        try:
            price = get_price(item)
        except Exception as e:  # rete/API non disponibile: non bloccare gli altri strumenti
            print(f"warn {item.get('symbol')}: {e}")
            continue
        if price is None:
            continue
        for key, msg in evaluate(item, price):
            if key in fired:
                continue
            try:
                send_telegram(msg + "\n\n_⚠️ Non è consulenza finanziaria._")
                fired[key] = {"price": price}
                changed = True
                print("ALERT:", msg)
            except Exception as e:
                print(f"errore invio Telegram: {e}")
        time.sleep(1.2)  # rispetta i rate limit delle API gratuite

    if changed:
        FIRED.write_text(json.dumps(fired, indent=2, ensure_ascii=False))
        print("fired.json aggiornato")
    else:
        print("nessun nuovo alert")


if __name__ == "__main__":
    main()
