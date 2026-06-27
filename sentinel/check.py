#!/usr/bin/env python3
"""Sentinella + Paper Trading (portafoglio simulato).

- Controlla i prezzi della watchlist (Finnhub per azioni/forex, CoinGecko per crypto).
- Gestisce un PORTAFOGLIO SIMULATO a soldi finti: apre/chiude posizioni seguendo
  entry zone / stop / target della watchlist, traccia cassa e profitti/perdite.
- Invia un messaggio Telegram per ogni operazione + un bilancio giornaliero.
- Aggiorna state/portfolio.json (dati) e PORTFOLIO.md (vista leggibile).

Nessun LLM, solo libreria standard di Python. Gira ogni ~5 min via GitHub Actions.
⚠️ SIMULAZIONE: soldi finti. Non è consulenza finanziaria.
"""
import json
import os
import time
import datetime
import urllib.request
import urllib.parse
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WATCHLIST = ROOT / "state" / "watchlist.json"
PORTFOLIO = ROOT / "state" / "portfolio.json"
PORTFOLIO_MD = ROOT / "PORTFOLIO.md"

FINNHUB_KEY = os.environ.get("MARKET_DATA_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Regole della simulazione (concordate con l'utente) ---
DEFAULT_CONFIG = {
    "starting_capital": 1000.0,    # capitale finto iniziale (USD)
    "max_per_trade_pct": 10,       # max % del capitale iniziale per operazione
    "max_open_positions": 5,       # posizioni aperte contemporaneamente
    "currency": "USD",             # i prezzi delle API sono in dollari
    "daily_summary_hour_utc": 19,  # ~21:00 ora italiana (CEST)
}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


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
    # Testo semplice (niente parse_mode): evita gli errori 400 di Telegram
    # quando il testo contiene caratteri che la formattazione Markdown rifiuta.
    if not (TG_TOKEN and TG_CHAT):
        print("Telegram non configurato: salto invio.")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20).read()
    except Exception as e:
        print(f"errore invio Telegram: {e}")


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def fmt(n):
    try:
        return f"{float(n):,.2f}"
    except Exception:
        return str(n)


def load_portfolio():
    p = load_json(PORTFOLIO, None) or {}
    p.setdefault("config", {})
    for k, v in DEFAULT_CONFIG.items():
        p["config"].setdefault(k, v)
    p.setdefault("cash", p["config"]["starting_capital"])
    p.setdefault("open_positions", [])
    p.setdefault("closed_trades", [])
    p.setdefault("last_summary_date", "")
    return p


def entry_condition(item, price):
    """Vero se il prezzo è entrato nella zona d'ingresso indicata dall'Analista."""
    ez = item.get("entry_zone")
    if not ez:
        return False
    lo, hi = min(ez), max(ez)
    direction = item.get("direction", "long")
    return (price <= hi) if direction == "long" else (price >= lo)


def exit_reason(pos, price):
    """Restituisce 'stop' o 'obiettivo' se la posizione va chiusa, altrimenti None."""
    direction = pos.get("direction", "long")
    stop = pos.get("stop")
    target = pos.get("target")
    if stop is not None:
        if (price <= stop) if direction == "long" else (price >= stop):
            return "stop"
    if target is not None:
        if (price >= target) if direction == "long" else (price <= target):
            return "obiettivo"
    return None


def pnl_for(pos, price):
    """Profitto/perdita (in valuta) sul capitale allocato a questa posizione."""
    entry = pos.get("entry_price") or 0
    if not entry:
        return 0.0
    sign = 1 if pos.get("direction", "long") == "long" else -1
    return sign * (price - entry) / entry * pos.get("amount", 0)


def write_portfolio_md(p, prices, equity, open_value):
    cfg = p["config"]
    cur = cfg["currency"]
    start = cfg["starting_capital"]
    chg = equity - start
    chgpct = (chg / start * 100.0) if start else 0.0
    wins = sum(1 for t in p["closed_trades"] if t.get("pnl", 0) >= 0)
    losses = sum(1 for t in p["closed_trades"] if t.get("pnl", 0) < 0)
    seg = "📈" if chg >= 0 else "📉"
    L = []
    L.append("# 📊 Portafoglio simulato (paper trading)")
    L.append("")
    L.append("> ⚠️ **SOLDI FINTI** — è una simulazione per imparare, non è consulenza finanziaria.")
    L.append("")
    L.append(f"_Aggiornato: {now_utc().strftime('%Y-%m-%d %H:%M UTC')}_")
    L.append("")
    L.append(f"## {seg} Bilancio")
    L.append("")
    L.append("| Voce | Valore |")
    L.append("|---|---|")
    L.append(f"| Capitale iniziale | {fmt(start)} {cur} |")
    L.append(f"| Cassa libera | {fmt(p['cash'])} {cur} |")
    L.append(f"| Valore posizioni aperte | {fmt(open_value)} {cur} |")
    L.append(f"| **Valore totale ora** | **{fmt(equity)} {cur}** |")
    L.append(f"| **Guadagno / Perdita** | **{'+' if chg >= 0 else ''}{fmt(chg)} {cur} ({'+' if chgpct >= 0 else ''}{chgpct:.1f}%)** |")
    L.append(f"| Operazioni chiuse | {len(p['closed_trades'])} (vinte {wins} / perse {losses}) |")
    L.append("")
    L.append("## Posizioni aperte")
    L.append("")
    if p["open_positions"]:
        L.append("| Strumento | Tipo | Entrata | Prezzo ora | P/L attuale | Stop | Obiettivo |")
        L.append("|---|---|---|---|---|---|---|")
        for pos in p["open_positions"]:
            price = prices.get(pos["symbol"])
            if price is not None:
                upnl = pnl_for(pos, price)
                upct = (upnl / pos["amount"] * 100.0) if pos.get("amount") else 0.0
                pl = f"{'+' if upnl >= 0 else ''}{fmt(upnl)} ({'+' if upct >= 0 else ''}{upct:.1f}%)"
                pnow = f"${fmt(price)}"
            else:
                pl, pnow = "—", "—"
            stop_s = f"${fmt(pos['stop'])}" if pos.get("stop") is not None else "—"
            tgt_s = f"${fmt(pos['target'])}" if pos.get("target") is not None else "—"
            L.append(f"| {pos['symbol']} | {pos.get('direction', 'long')} | ${fmt(pos['entry_price'])} | {pnow} | {pl} | {stop_s} | {tgt_s} |")
    else:
        L.append("_Nessuna posizione aperta al momento._")
    L.append("")
    L.append("## Ultime operazioni chiuse")
    L.append("")
    closed = p["closed_trades"][-15:][::-1]
    if closed:
        L.append("| Strumento | Entrata | Uscita | Risultato | Motivo | Chiusa il |")
        L.append("|---|---|---|---|---|---|")
        for t in closed:
            res = f"{'+' if t.get('pnl', 0) >= 0 else ''}{fmt(t.get('pnl', 0))} ({'+' if t.get('pnl_pct', 0) >= 0 else ''}{t.get('pnl_pct', 0):.1f}%)"
            when = str(t.get("closed_at", ""))[:16].replace("T", " ")
            L.append(f"| {t['symbol']} | ${fmt(t.get('entry_price', 0))} | ${fmt(t.get('exit_price', 0))} | {res} | {t.get('reason', '')} | {when} |")
    else:
        L.append("_Ancora nessuna operazione chiusa._")
    L.append("")
    PORTFOLIO_MD.write_text("\n".join(L), encoding="utf-8")


def main():
    existed = PORTFOLIO.exists()
    wl = load_json(WATCHLIST, {"items": []})
    portfolio = load_portfolio()
    cfg = portfolio["config"]
    per_trade = cfg["starting_capital"] * cfg["max_per_trade_pct"] / 100.0

    items = wl.get("items", [])

    # Per ogni simbolo serve un modo per recuperare il prezzo: dalla watchlist
    # o, per le posizioni aperte non più in watchlist, dai dati salvati nella posizione.
    price_inputs = {it["symbol"]: it for it in items}
    for pos in portfolio["open_positions"]:
        price_inputs.setdefault(pos["symbol"], {
            "symbol": pos["symbol"],
            "asset_class": pos.get("asset_class"),
            "cg_id": pos.get("cg_id"),
        })

    prices = {}
    for sym, src in price_inputs.items():
        try:
            prices[sym] = get_price(src)
        except Exception as e:
            print(f"warn prezzo {sym}: {e}")
            prices[sym] = None
        time.sleep(1.2)  # rispetta i rate limit delle API gratuite

    dirty = not existed  # alla primissima esecuzione crea i file
    open_by_symbol = {p["symbol"]: p for p in portfolio["open_positions"]}

    # 1) CHIUSURE — controlla le posizioni aperte (stop / obiettivo)
    still_open = []
    for pos in portfolio["open_positions"]:
        price = prices.get(pos["symbol"])
        if price is None:
            still_open.append(pos)
            continue
        reason = exit_reason(pos, price)
        if not reason:
            still_open.append(pos)
            continue
        realized = pnl_for(pos, price)
        portfolio["cash"] += pos.get("amount", 0) + realized
        pct = (realized / pos["amount"] * 100.0) if pos.get("amount") else 0.0
        closed = dict(pos)
        closed.update({
            "exit_price": price,
            "pnl": round(realized, 2),
            "pnl_pct": round(pct, 2),
            "reason": reason,
            "closed_at": now_utc().isoformat(timespec="seconds"),
        })
        portfolio["closed_trades"].append(closed)
        emoji = "🎯" if reason == "obiettivo" else "🛑"
        esito = "GUADAGNO" if realized >= 0 else "PERDITA"
        send_telegram(
            f"{emoji} SIMULAZIONE — VENDUTO {pos['symbol']}\n"
            f"Prezzo: ${fmt(price)} (entrata ${fmt(pos['entry_price'])})\n"
            f"Risultato: {'+' if realized >= 0 else ''}{fmt(realized)} {cfg['currency']} "
            f"({'+' if pct >= 0 else ''}{pct:.1f}%) — {esito}\n"
            f"Motivo: {reason}\n\n⚠️ Soldi finti. Non è consulenza finanziaria."
        )
        dirty = True
    portfolio["open_positions"] = still_open
    open_by_symbol = {p["symbol"]: p for p in portfolio["open_positions"]}

    # 2) APERTURE — segnali d'ingresso dalla watchlist
    for it in items:
        sym = it["symbol"]
        price = prices.get(sym)
        if price is None or sym in open_by_symbol:
            continue
        if not entry_condition(it, price):
            continue
        if len(portfolio["open_positions"]) >= cfg["max_open_positions"]:
            continue  # portafoglio pieno
        if portfolio["cash"] < per_trade:
            continue  # cassa insufficiente
        amount = per_trade
        targets = it.get("targets") or []
        pos = {
            "symbol": sym,
            "asset_class": it.get("asset_class"),
            "cg_id": it.get("cg_id"),
            "direction": it.get("direction", "long"),
            "entry_price": price,
            "amount": round(amount, 2),
            "qty": amount / price,
            "stop": it.get("stop"),
            "target": targets[0] if targets else None,
            "note": it.get("note", ""),
            "opened_at": now_utc().isoformat(timespec="seconds"),
        }
        portfolio["open_positions"].append(pos)
        open_by_symbol[sym] = pos
        portfolio["cash"] -= amount
        azione = "COMPRATO" if pos["direction"] == "long" else "VENDUTO ALLO SCOPERTO"
        stop_s = f"${fmt(pos['stop'])}" if pos["stop"] is not None else "—"
        tgt_s = f"${fmt(pos['target'])}" if pos["target"] is not None else "—"
        send_telegram(
            f"📈 SIMULAZIONE — {azione} {sym}\n"
            f"Prezzo: ${fmt(price)} — investiti {fmt(amount)} {cfg['currency']}\n"
            f"Stop: {stop_s} / Obiettivo: {tgt_s}\n"
            f"{pos['note']}\n\n⚠️ Soldi finti. Non è consulenza finanziaria."
        )
        dirty = True

    # 3) Valore di mercato delle posizioni + patrimonio totale
    open_value = 0.0
    for pos in portfolio["open_positions"]:
        price = prices.get(pos["symbol"])
        open_value += pos.get("amount", 0) + (pnl_for(pos, price) if price is not None else 0.0)
    equity = portfolio["cash"] + open_value

    # 4) Bilancio giornaliero (una volta al giorno, la sera)
    today = now_utc().strftime("%Y-%m-%d")
    if now_utc().hour >= cfg["daily_summary_hour_utc"] and portfolio.get("last_summary_date") != today:
        start = cfg["starting_capital"]
        chg = equity - start
        chgpct = (chg / start * 100.0) if start else 0.0
        wins = sum(1 for t in portfolio["closed_trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in portfolio["closed_trades"] if t.get("pnl", 0) < 0)
        send_telegram(
            f"📊 SIMULAZIONE — Bilancio giornaliero\n"
            f"Capitale: {fmt(start)} → {fmt(equity)} {cfg['currency']} "
            f"({'+' if chg >= 0 else ''}{fmt(chg)}, {'+' if chgpct >= 0 else ''}{chgpct:.1f}%)\n"
            f"Posizioni aperte: {len(portfolio['open_positions'])} · "
            f"Chiuse: {len(portfolio['closed_trades'])} (vinte {wins} / perse {losses})\n\n"
            f"⚠️ Soldi finti. Non è consulenza finanziaria."
        )
        portfolio["last_summary_date"] = today
        dirty = True

    # 5) Salva (solo se è cambiato qualcosa, per non intasare lo storico dei commit)
    if dirty:
        PORTFOLIO.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
        write_portfolio_md(portfolio, prices, equity, open_value)
        print(f"portafoglio aggiornato — patrimonio {fmt(equity)} {cfg['currency']}")
    else:
        print("nessuna operazione, nessun aggiornamento")


if __name__ == "__main__":
    main()
