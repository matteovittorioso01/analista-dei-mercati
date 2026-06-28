#!/usr/bin/env python3
"""Motore di BACKTEST per strategie a regole — la prova del nove prima dei soldi veri.

Perché esiste: la strategia "Claude legge le news e sceglie" NON è testabile sul
passato (non puoi rigiocare le notizie storiche dentro un'AI). Quindi non sapremo
mai, prima di rischiare, se ha un vantaggio. Una strategia a REGOLE invece sì: la
si fa girare su anni di dati storici e si misura se batte il semplice "compra e
tieni" *al netto dei costi*. Questo separa una strategia da una scommessa.

Cosa fa:
  - Scarica prezzi storici giornalieri (Stooq per azioni/ETF/forex, CoinGecko per
    crypto) oppure legge un CSV locale (Date,Close).
  - Applica una strategia a regole (di base: incrocio di medie mobili).
  - Conta i COSTI di transazione a ogni cambio di posizione.
  - Stampa metriche aggiustate per il rischio E il confronto con buy & hold.

Esempi:
  python backtest/engine.py --source stooq --symbol spy.us --fast 50 --slow 200
  python backtest/engine.py --source coingecko --symbol bitcoin --days 730
  python backtest/engine.py --source csv --file prezzi.csv

Solo libreria standard. ⚠️ Risultati passati non garantiscono risultati futuri.
"""
import argparse
import json
import math
import urllib.request
import urllib.parse

TRADING_DAYS = 252


# ----------------------------- dati -----------------------------------------
def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def load_stooq(symbol):
    """Prezzi giornalieri da Stooq (gratis, senza chiave). Es: 'spy.us', 'eurusd', '^spx'."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol)}&i=d"
    text = http_get(url)
    rows = []
    for i, line in enumerate(text.splitlines()):
        if i == 0 or not line.strip():
            continue
        c = line.split(",")
        # Date,Open,High,Low,Close,Volume
        try:
            rows.append((c[0], float(c[4])))
        except (IndexError, ValueError):
            continue
    return rows


def load_coingecko(cg_id, days):
    """Prezzi giornalieri crypto da CoinGecko (gratis)."""
    url = (f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(cg_id)}"
           f"/market_chart?vs_currency=usd&days={int(days)}&interval=daily")
    d = json.loads(http_get(url))
    return [(str(int(ts)), float(px)) for ts, px in d.get("prices", [])]


def load_csv(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            c = line.strip().split(",")
            if i == 0 and not c[-1].replace(".", "", 1).isdigit():
                continue  # header
            try:
                rows.append((c[0], float(c[-1])))
            except (IndexError, ValueError):
                continue
    return rows


# --------------------------- strategia --------------------------------------
def sma(values, window):
    """Media mobile semplice; None finché non c'è abbastanza storico."""
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        out.append(s / window if i >= window - 1 else None)
    return out


def signal_sma_cross(closes, fast, slow):
    """1 = investito (fast>=slow), 0 = liquidità. Long-only, decisione sulla chiusura."""
    f, s = sma(closes, fast), sma(closes, slow)
    sig = []
    for i in range(len(closes)):
        if f[i] is None or s[i] is None:
            sig.append(0)
        else:
            sig.append(1 if f[i] >= s[i] else 0)
    return sig


# --------------------------- backtest ---------------------------------------
def run_backtest(prices, signal, cost_side_pct):
    """Simula la strategia. La posizione di oggi agisce sul rendimento di DOMANI
    (niente sguardo nel futuro). Costo applicato a ogni cambio di posizione.
    Restituisce (equity_strategia, equity_buyhold, n_trade)."""
    closes = [p for _, p in prices]
    eq, bh = [1.0], [1.0]
    pos_prev, n_trades = 0, 0
    cost = cost_side_pct / 100.0
    for i in range(1, len(closes)):
        ret = closes[i] / closes[i - 1] - 1.0
        pos = signal[i - 1]  # posizione decisa ieri in chiusura
        e = eq[-1] * (1.0 + pos * ret)
        if pos != pos_prev:           # cambio di posizione -> paga il costo
            e *= (1.0 - cost)
            n_trades += 1
            pos_prev = pos
        eq.append(e)
        bh.append(bh[-1] * (1.0 + ret))
    return eq, bh, n_trades


# --------------------------- metriche ---------------------------------------
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def metrics(eq):
    rets = [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq))]
    total = (eq[-1] / eq[0] - 1.0) * 100.0 if eq else 0.0
    cagr = ((eq[-1] / eq[0]) ** (TRADING_DAYS / len(rets)) - 1.0) * 100.0 if rets and eq[0] else 0.0
    vol = _std(rets) * math.sqrt(TRADING_DAYS) * 100.0
    sharpe = (_mean(rets) / _std(rets) * math.sqrt(TRADING_DAYS)) if _std(rets) else 0.0
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return {"total": total, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd * 100.0}


def fmt_metrics(name, m):
    return (f"{name:<14} ret {m['total']:+8.2f}%  CAGR {m['cagr']:+7.2f}%  "
            f"vol {m['vol']:6.2f}%  Sharpe {m['sharpe']:5.2f}  maxDD {m['mdd']:7.2f}%")


def main():
    ap = argparse.ArgumentParser(description="Backtest strategie a regole (soldi finti).")
    ap.add_argument("--source", choices=["stooq", "coingecko", "csv"], required=True)
    ap.add_argument("--symbol", help="ticker Stooq (es. spy.us) o id CoinGecko (es. bitcoin)")
    ap.add_argument("--file", help="percorso CSV (con --source csv): colonne Date,...,Close")
    ap.add_argument("--days", type=int, default=730, help="giorni storici per CoinGecko")
    ap.add_argument("--strategy", choices=["sma"], default="sma")
    ap.add_argument("--fast", type=int, default=50)
    ap.add_argument("--slow", type=int, default=200)
    ap.add_argument("--cost", type=float, default=0.1, help="costo per operazione, %% (default 0.1)")
    args = ap.parse_args()

    if args.source == "stooq":
        prices = load_stooq(args.symbol)
    elif args.source == "coingecko":
        prices = load_coingecko(args.symbol, args.days)
    else:
        prices = load_csv(args.file)

    if len(prices) < args.slow + 5:
        print(f"Dati insufficienti: {len(prices)} barre (servono almeno {args.slow + 5}).")
        return

    sig = signal_sma_cross([p for _, p in prices], args.fast, args.slow)
    eq, bh, n_trades = run_backtest(prices, sig, args.cost)
    m_strat, m_bh = metrics(eq), metrics(bh)

    label = f"{args.symbol or args.file} ({len(prices)} barre, {prices[0][0]}->{prices[-1][0]})"
    print(f"=== BACKTEST  SMA {args.fast}/{args.slow}  costo {args.cost}%/op  —  {label} ===\n")
    print(fmt_metrics("Strategia", m_strat))
    print(fmt_metrics("Buy & hold", m_bh))
    print(f"\nOperazioni della strategia: {n_trades}")
    verdetto = "BATTE" if m_strat["sharpe"] > m_bh["sharpe"] else "NON batte"
    print(f"Verdetto (per Sharpe): la strategia {verdetto} il semplice comprare e tenere.")
    print("\n⚠️ Backtest = passato. Non garantisce il futuro. Attento all'over-fitting:")
    print("   se provi 100 combinazioni di parametri, qualcuna sembrera' ottima per caso.")


if __name__ == "__main__":
    main()
