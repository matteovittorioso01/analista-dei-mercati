#!/usr/bin/env python3
"""Motore di BACKTEST per strategie a regole — la prova del nove prima dei soldi veri.

Perché esiste: la strategia "Claude legge le news e sceglie" NON è testabile sul
passato (non puoi rigiocare le notizie storiche dentro un'AI). Quindi non sapremo
mai, prima di rischiare, se ha un vantaggio. Una strategia a REGOLE invece sì: la
si fa girare su anni di dati storici e si misura se batte il semplice "compra e
tieni" *al netto dei costi*. Questo separa una strategia da una scommessa.

Strategie incluse (tutte long-only: investito oppure liquidità):
  - sma       : trend-following con incrocio di medie mobili (fast/slow)
  - rsi       : mean-reversion (compra ipervenduto, vende quando rientra)
  - breakout  : momentum stile Donchian (compra i nuovi massimi)

Dati: Stooq (azioni/ETF/forex, gratis), CoinGecko (crypto, gratis) o un CSV locale.

Esempi:
  python backtest/engine.py --source stooq --symbol spy.us --strategy sma --fast 50 --slow 200
  python backtest/engine.py --source coingecko --symbol bitcoin --days 730 --strategy breakout
  python backtest/engine.py --source csv --file prezzi.csv --strategy rsi

Importabile: evaluate(prices, "sma", cost=0.1, fast=50, slow=200) -> dict di metriche.
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
        c = line.split(",")  # Date,Open,High,Low,Close,Volume
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


# ----------------------- indicatori e segnali -------------------------------
def sma(values, window):
    """Media mobile semplice; None finché non c'è abbastanza storico."""
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        out.append(s / window if i >= window - 1 else None)
    return out


def rsi(values, period=14):
    """RSI di Wilder; None finché non c'è abbastanza storico."""
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(values)):
        ch = values[i] - values[i - 1]
        avg_g = (avg_g * (period - 1) + max(ch, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-ch, 0.0)) / period
        out[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    return out


def signal_sma(closes, fast=50, slow=200):
    """Trend-following: investito quando la media veloce è sopra la lenta."""
    f, s = sma(closes, fast), sma(closes, slow)
    return [1 if (f[i] is not None and s[i] is not None and f[i] >= s[i]) else 0
            for i in range(len(closes))]


def signal_rsi(closes, period=14, low=30, high=55):
    """Mean-reversion: entra quando RSI < low (ipervenduto), esce quando RSI > high."""
    r = rsi(closes, period)
    sig, pos = [], 0
    for i in range(len(closes)):
        if r[i] is not None:
            if pos == 0 and r[i] < low:
                pos = 1
            elif pos == 1 and r[i] > high:
                pos = 0
        sig.append(pos)
    return sig


def signal_breakout(closes, entry_n=20, exit_n=10):
    """Momentum (Donchian): entra sul nuovo massimo a entry_n giorni,
    esce sul nuovo minimo a exit_n giorni."""
    sig, pos = [], 0
    for i in range(len(closes)):
        if i >= entry_n:
            hh = max(closes[i - entry_n:i])
            ll = min(closes[i - exit_n:i]) if i >= exit_n else None
            if pos == 0 and closes[i] >= hh:
                pos = 1
            elif pos == 1 and ll is not None and closes[i] <= ll:
                pos = 0
        sig.append(pos)
    return sig


STRATEGIES = {"sma": signal_sma, "rsi": signal_rsi, "breakout": signal_breakout}


# --------------------------- backtest ---------------------------------------
def run_backtest(prices, signal, cost_side_pct):
    """La posizione di oggi agisce sul rendimento di DOMANI (niente sguardo nel
    futuro). Costo applicato a ogni cambio di posizione. Ritorna (eq, buyhold, n)."""
    closes = [p for _, p in prices]
    eq, bh = [1.0], [1.0]
    pos_prev, n_trades = 0, 0
    cost = cost_side_pct / 100.0
    for i in range(1, len(closes)):
        ret = closes[i] / closes[i - 1] - 1.0
        pos = signal[i - 1]
        e = eq[-1] * (1.0 + pos * ret)
        if pos != pos_prev:
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
    peak, mdd = (eq[0] if eq else 0.0), 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return {"total": total, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd * 100.0}


def evaluate(prices, strategy="sma", cost=0.1, **params):
    """API importabile: ritorna metriche strategia + buy&hold + n. operazioni."""
    sig = STRATEGIES[strategy]([p for _, p in prices], **params)
    eq, bh, n = run_backtest(prices, sig, cost)
    return {"strategy": metrics(eq), "buyhold": metrics(bh), "n_trades": n,
            "bars": len(prices), "first": prices[0][0], "last": prices[-1][0]}


def fmt_metrics(name, m):
    return (f"{name:<14} ret {m['total']:+8.2f}%  CAGR {m['cagr']:+7.2f}%  "
            f"vol {m['vol']:6.2f}%  Sharpe {m['sharpe']:5.2f}  maxDD {m['mdd']:7.2f}%")


def main():
    ap = argparse.ArgumentParser(description="Backtest strategie a regole (soldi finti).")
    ap.add_argument("--source", choices=["stooq", "coingecko", "csv"], required=True)
    ap.add_argument("--symbol", help="ticker Stooq (es. spy.us) o id CoinGecko (es. bitcoin)")
    ap.add_argument("--file", help="percorso CSV (con --source csv)")
    ap.add_argument("--days", type=int, default=730, help="giorni storici per CoinGecko")
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="sma")
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

    need = max(args.slow, 30) + 5
    if len(prices) < need:
        print(f"Dati insufficienti: {len(prices)} barre (servono almeno {need}).")
        return

    params = {"fast": args.fast, "slow": args.slow} if args.strategy == "sma" else {}
    res = evaluate(prices, args.strategy, args.cost, **params)
    label = f"{args.symbol or args.file} ({res['bars']} barre, {res['first']}->{res['last']})"
    print(f"=== BACKTEST  {args.strategy}  costo {args.cost}%/op  —  {label} ===\n")
    print(fmt_metrics("Strategia", res["strategy"]))
    print(fmt_metrics("Buy & hold", res["buyhold"]))
    print(f"\nOperazioni della strategia: {res['n_trades']}")
    verdetto = "BATTE" if res["strategy"]["sharpe"] > res["buyhold"]["sharpe"] else "NON batte"
    print(f"Verdetto (per Sharpe): la strategia {verdetto} il semplice comprare e tenere.")
    print("\n⚠️ Backtest = passato. Non garantisce il futuro. Attento all'over-fitting:")
    print("   se provi 100 combinazioni di parametri, qualcuna sembrera' ottima per caso.")


if __name__ == "__main__":
    main()
