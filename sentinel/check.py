#!/usr/bin/env python3
"""Sentinella + Paper Trading (portafoglio simulato).

- Controlla i prezzi della watchlist (Finnhub per azioni/forex, CoinGecko per crypto).
- Gestisce un PORTAFOGLIO SIMULATO a soldi finti: apre/chiude posizioni seguendo
  entry zone / stop / target della watchlist, traccia cassa e profitti/perdite.
- Applica lo STOP-LOSS DURO a -7% (rete di sicurezza, ogni 5 min).
- Esegue gli ordini di RIBILANCIAMENTO lasciati dal Risk Manager (state/risk_orders.json).
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
RISK_ORDERS = ROOT / "state" / "risk_orders.json"
PORTFOLIO_MD = ROOT / "PORTFOLIO.md"
EQUITY_HISTORY = ROOT / "state" / "equity_history.csv"

FINNHUB_KEY = os.environ.get("MARKET_DATA_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Regole della simulazione (concordate con l'utente) ---
DEFAULT_CONFIG = {
    "starting_capital": 1000.0,        # capitale finto iniziale (USD)
    "max_per_trade_pct": 10,           # max % del capitale iniziale per operazione
    "max_open_positions": 5,           # posizioni aperte contemporaneamente
    "max_positions_per_category": 1,   # anti-concentrazione: max posizioni nella stessa categoria
                                       # (1 = una sola per Crypto/Azioni/Materie prime/Valute -> spread tra asset class)
    "max_per_category_pct": 35,        # anti-concentrazione: max % del portafoglio per categoria
    "currency": "USD",                 # i prezzi delle API sono in dollari
    "daily_summary_hour_utc": 19,      # ~21:00 ora italiana (CEST)
    "hard_stop_loss_pct": -7,          # rete di sicurezza: chiudi se sotto questa %
    "round_trip_cost_pct": 0.2,        # costi realistici (commissioni+spread) per operazione completa
    "max_drawdown_pct": -20,           # circuit breaker: sospendi NUOVE aperture se il capitale
                                       # scende oltre questa % sotto il massimo storico (picco)
}

# Le "categorie" raggruppano gli asset per il controllo di diversificazione.
# Tenere allineata a quella di risk/portfolio_report.py.
CATEGORIE = {
    "crypto": "Crypto",
    "us_stock": "Azioni",
    "eu_stock": "Azioni",
    "commodity": "Materie prime",
    "forex": "Valute",
}


def category_of(asset_class):
    return CATEGORIE.get(asset_class, "Altro")


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def price_finnhub(symbol):
    """Prezzo azioni USA ed ETF (anche proxy di indici/materie prime) via Finnhub.

    Richiede MARKET_DATA_API_KEY. Sul piano gratuito Finnhub copre azioni/ETF
    quotati negli USA: per oro/petrolio/indici usare ETF proxy (es. GLD, USO,
    SPY, QQQ), non i simboli spot (XAUUSD, BRENT) che non vengono prezzati.
    """
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


def price_frankfurter(symbol):
    """Cambio forex spot via Frankfurter (dati BCE, gratis, senza chiave).

    `symbol` = 6 lettere BASEQUOTE, es. 'EURUSD' o 'USDJPY'. Restituisce quante
    unita' di QUOTE vale 1 unita' di BASE. Nota: i tassi BCE si aggiornano una
    volta al giorno nei giorni feriali (adatto a trade swing, non intraday) e
    coprono solo le valute principali pubblicate dalla BCE.
    """
    s = (symbol or "").upper().replace("/", "")
    if len(s) != 6:
        return None
    base, quote = s[:3], s[3:]
    url = f"https://api.frankfurter.app/latest?from={urllib.parse.quote(base)}&to={urllib.parse.quote(quote)}"
    d = http_get_json(url)
    v = d.get("rates", {}).get(quote)
    return float(v) if v else None


def get_price(item):
    ac = item.get("asset_class")
    if ac == "crypto":
        return price_coingecko(item.get("cg_id") or item["symbol"].lower())
    if ac == "forex":
        return price_frankfurter(item["symbol"])
    # us_stock / eu_stock / commodity -> ticker quotabile su Finnhub (ETF proxy)
    return price_finnhub(item["symbol"])


def send_telegram(text):
    # Testo semplice (niente parse_mode): evita gli errori 400 di Telegram.
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
    p.setdefault("last_orders_stamp", "")
    p.setdefault("peak_equity", p["config"]["starting_capital"])  # max storico, per il drawdown
    p.setdefault("last_breaker_alert_date", "")
    return p


def round_trip_cost(amount, cfg):
    """Costo di transazione (commissioni + spread) su una chiusura, in valuta.

    Modellato come una % dell'importo movimentato e addebitato alla chiusura.
    Approssimazione onesta per non illudersi con un paper trading "a costo zero":
    moltissime strategie redditizie sulla carta diventano in perdita coi costi reali.
    """
    return abs(amount) * cfg.get("round_trip_cost_pct", 0.0) / 100.0


def append_equity_point(equity, cash, open_value, n_open, n_closed):
    """Aggiunge una riga giornaliera allo storico del capitale (curva equity).

    Serve a misurare nel tempo rendimento, volatilità e drawdown (vedi
    risk/performance.py). Una riga al giorno, formato CSV semplice.
    """
    new = not EQUITY_HISTORY.exists()
    row = (f"{now_utc().strftime('%Y-%m-%d')},{equity:.2f},{cash:.2f},"
           f"{open_value:.2f},{n_open},{n_closed}\n")
    with EQUITY_HISTORY.open("a", encoding="utf-8") as f:
        if new:
            f.write("date,equity,cash,open_value,n_open,n_closed\n")
        f.write(row)


def entry_condition(item, price):
    """Vero se il prezzo è entrato nella zona d'ingresso indicata dall'Analista."""
    ez = item.get("entry_zone")
    if not ez:
        return False
    lo, hi = min(ez), max(ez)
    direction = item.get("direction", "long")
    return (price <= hi) if direction == "long" else (price >= lo)


def exit_reason(pos, price, hard_stop_pct=-7):
    """Restituisce il motivo di chiusura ('stop -7%', 'stop', 'obiettivo') o None."""
    direction = pos.get("direction", "long")
    entry = pos.get("entry_price") or 0
    sign = 1 if direction == "long" else -1
    # Rete di sicurezza: perdita oltre la soglia -> chiudi comunque
    if entry and sign * (price - entry) / entry * 100 <= hard_stop_pct:
        return f"stop {hard_stop_pct}%"
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


def execute_risk_orders(portfolio, prices, cfg):
    """Esegue gli ordini del Risk Manager (state/risk_orders.json).

    v1: eseguiamo solo le VENDITE (controllo del rischio / diversificazione).
    Gli acquisti restano gestiti dalle idee della watchlist. Restituisce True
    se è cambiato qualcosa.
    """
    ro = load_json(RISK_ORDERS, {})
    stamp = ro.get("updated_at", "")
    if not stamp or portfolio.get("last_orders_stamp") == stamp:
        return False  # nessun nuovo set di ordini

    changed = False
    by_sym = {p["symbol"]: p for p in portfolio["open_positions"]}
    for o in ro.get("orders", []):
        action = (o.get("action") or "").upper()
        sym = o.get("ticker")
        if action != "SELL" or sym not in by_sym:
            continue
        pos = by_sym[sym]
        price = prices.get(sym)
        if price is None:
            continue
        try:
            frac = float(o.get("percentage_to_trade") or 1.0)
        except (TypeError, ValueError):
            frac = 1.0
        if frac <= 0:
            continue
        frac = min(frac, 1.0)
        entry = pos.get("entry_price") or price
        sign = 1 if pos.get("direction", "long") == "long" else -1
        sold_amount = pos.get("amount", 0) * frac
        realized = sign * (price - entry) / entry * sold_amount
        realized -= round_trip_cost(sold_amount, cfg)  # costi reali di transazione
        portfolio["cash"] += sold_amount + realized
        pct = (realized / sold_amount * 100) if sold_amount else 0.0
        totale = frac >= 0.999
        portfolio["closed_trades"].append({
            "symbol": sym,
            "asset_class": pos.get("asset_class"),
            "cg_id": pos.get("cg_id"),
            "direction": pos.get("direction", "long"),
            "entry_price": entry,
            "amount": round(sold_amount, 2),
            "exit_price": price,
            "pnl": round(realized, 2),
            "pnl_pct": round(pct, 2),
            "reason": "ribilanciamento" + (" (totale)" if totale else " (parziale)"),
            "closed_at": now_utc().isoformat(timespec="seconds"),
        })
        if totale:
            portfolio["open_positions"] = [x for x in portfolio["open_positions"] if x["symbol"] != sym]
            by_sym.pop(sym, None)
        else:
            pos["amount"] = round(pos.get("amount", 0) * (1 - frac), 2)
            pos["qty"] = pos.get("qty", 0) * (1 - frac)
        quanto = "tutto" if totale else f"{frac * 100:.0f}%"
        send_telegram(
            f"♻️ SIMULAZIONE — RIBILANCIAMENTO: venduto {quanto} di {sym}\n"
            f"Prezzo: ${fmt(price)} — risultato {'+' if realized >= 0 else ''}{fmt(realized)} {cfg['currency']} "
            f"({'+' if pct >= 0 else ''}{pct:.1f}%)\n"
            f"Motivo: {o.get('reasoning', 'controllo rischio / diversificazione')}\n\n"
            f"⚠️ Soldi finti. Non è consulenza finanziaria."
        )
        changed = True

    portfolio["last_orders_stamp"] = stamp
    return changed


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
    hard_stop = cfg.get("hard_stop_loss_pct", -7)

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

    # 1) CHIUSURE — controlla le posizioni aperte (stop / obiettivo / stop-loss -7%)
    still_open = []
    for pos in portfolio["open_positions"]:
        price = prices.get(pos["symbol"])
        if price is None:
            still_open.append(pos)
            continue
        reason = exit_reason(pos, price, hard_stop)
        if not reason:
            still_open.append(pos)
            continue
        realized = pnl_for(pos, price)
        realized -= round_trip_cost(pos.get("amount", 0), cfg)  # costi reali di transazione
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

    # 1b) RIBILANCIAMENTO — esegui gli ordini (solo vendite) del Risk Manager
    if execute_risk_orders(portfolio, prices, cfg):
        dirty = True
    open_by_symbol = {p["symbol"]: p for p in portfolio["open_positions"]}

    # Esposizione corrente per categoria (valore di mercato e numero di posizioni)
    # e patrimonio stimato: servono al freno anti-concentrazione qui sotto.
    # Aprire a mercato non cambia il patrimonio (sposta cassa -> posizione), quindi
    # equity_now resta una base valida per tutto il loop di apertura.
    max_cat_n = cfg.get("max_positions_per_category", 1)
    max_cat_pct = cfg.get("max_per_category_pct", 35)
    cat_value, cat_count, open_market_value = {}, {}, 0.0
    for pos in portfolio["open_positions"]:
        pr = prices.get(pos["symbol"])
        val = pos.get("amount", 0) + (pnl_for(pos, pr) if pr is not None else 0.0)
        open_market_value += val
        c = category_of(pos.get("asset_class"))
        cat_value[c] = cat_value.get(c, 0.0) + val
        cat_count[c] = cat_count.get(c, 0) + 1
    equity_now = portfolio["cash"] + open_market_value

    # CIRCUIT BREAKER — aggiorna il picco storico e calcola il drawdown attuale.
    # Se il capitale è sceso oltre la soglia sotto il picco, sospendiamo le NUOVE
    # aperture (le posizioni in essere restano gestite da stop/target). È la rete
    # che impedisce di "raddoppiare nel buco" durante una serie negativa.
    peak = max(portfolio.get("peak_equity", cfg["starting_capital"]), equity_now)
    portfolio["peak_equity"] = peak
    dd_pct = (equity_now - peak) / peak * 100.0 if peak else 0.0
    max_dd = cfg.get("max_drawdown_pct", -100)
    entries_halted = dd_pct <= max_dd
    if entries_halted:
        print(f"CIRCUIT BREAKER attivo: drawdown {dd_pct:.1f}% <= {max_dd}% — nuove aperture sospese")
        today_str = now_utc().strftime("%Y-%m-%d")
        if portfolio.get("last_breaker_alert_date") != today_str:
            send_telegram(
                f"🛑 SIMULAZIONE — CIRCUIT BREAKER attivo\n"
                f"Capitale sceso del {dd_pct:.1f}% dal massimo (soglia {max_dd}%).\n"
                f"Sospendo le NUOVE aperture finché non si recupera. Le posizioni aperte "
                f"restano gestite da stop e obiettivo.\n\n"
                f"⚠️ Soldi finti. Non è consulenza finanziaria."
            )
            portfolio["last_breaker_alert_date"] = today_str
            dirty = True

    # 2) APERTURE — segnali d'ingresso dalla watchlist
    for it in items:
        if entries_halted:
            break  # circuit breaker: nessuna nuova apertura
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
        # Freno anti-concentrazione: non aprire se la categoria è già piena o se
        # l'ingresso la porterebbe oltre il tetto di peso (es. due crypto correlate).
        cat = category_of(it.get("asset_class"))
        projected_pct = (cat_value.get(cat, 0.0) + per_trade) / equity_now * 100.0 if equity_now else 0.0
        if cat_count.get(cat, 0) >= max_cat_n:
            print(f"salto {sym}: categoria {cat} gia' al limite di posizioni ({cat_count.get(cat, 0)}/{max_cat_n})")
            continue
        if projected_pct > max_cat_pct:
            print(f"salto {sym}: categoria {cat} supererebbe il tetto di peso ({projected_pct:.0f}% > {max_cat_pct}%)")
            continue
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
        cat_value[cat] = cat_value.get(cat, 0.0) + amount
        cat_count[cat] = cat_count.get(cat, 0) + 1
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
        peak = max(portfolio.get("peak_equity", start), equity)
        portfolio["peak_equity"] = peak
        dd = (equity - peak) / peak * 100.0 if peak else 0.0
        append_equity_point(equity, portfolio["cash"], open_value,
                            len(portfolio["open_positions"]), len(portfolio["closed_trades"]))
        send_telegram(
            f"📊 SIMULAZIONE — Bilancio giornaliero\n"
            f"Capitale: {fmt(start)} → {fmt(equity)} {cfg['currency']} "
            f"({'+' if chg >= 0 else ''}{fmt(chg)}, {'+' if chgpct >= 0 else ''}{chgpct:.1f}%)\n"
            f"Drawdown dal massimo: {dd:.1f}%\n"
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
