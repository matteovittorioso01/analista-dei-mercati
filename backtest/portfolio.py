#!/usr/bin/env python3
"""Confronto di PANIERI DIVERSIFICATI (buy & hold con ribilanciamento annuale).

Il backtest delle strategie attive ha mostrato che battere il mercato è difficile.
Questo strumento guarda invece la strada che i dati premiano: **tenere un paniere
diversificato**. Confronta alcune allocazioni classiche su anni di storia reale e
mostra, per ognuna, rendimento, oscillazioni (volatilità) e — la cosa che conta di
più — la **perdita massima** subita lungo la strada (max drawdown).

Lo scopo non è dirti "compra questo": è farti VEDERE il compromesso tra crescita e
tranquillità, così scegli con consapevolezza il mix adatto al tuo orizzonte e al tuo
stomaco. Più azioni = più crescita ma cadute più dure; più obbligazioni/oro = corsa
più morbida ma crescita minore.

Dati: Yahoo Finance (gratis, senza chiave). Solo libreria standard.
⚠️ Non è consulenza finanziaria. Il passato non garantisce il futuro.
"""
import os
import sys
import pathlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "backtest" / "results"

REBALANCE_COST = 0.001  # 0,1% sul capitale ribilanciato ogni anno (stima conservativa)

# Allocazioni classiche, dalla più aggressiva alla più prudente.
# VT=azioni mondiali, BND=obbligazioni USA, TLT=obbligazioni lunghe, GLD=oro, BIL=liquidità.
PORTFOLIOS = {
    "100% Azioni mondiali":          {"VT": 1.00},
    "80/20 (azioni/obbligazioni)":   {"VT": 0.80, "BND": 0.20},
    "60/40 bilanciato":              {"VT": 0.60, "BND": 0.40},
    "40/60 prudente":                {"VT": 0.40, "BND": 0.60},
    "Permanent Portfolio":           {"VT": 0.25, "TLT": 0.25, "GLD": 0.25, "BIL": 0.25},
}


def all_tickers(portfolios):
    s = set()
    for w in portfolios.values():
        s.update(w)
    return sorted(s)


def year_of(ts_str):
    return datetime.fromtimestamp(int(ts_str), tz=timezone.utc).year


def fetch_all(tickers, fetcher):
    """Ritorna {ticker: {date: price}} e segnala i ticker non scaricabili."""
    data, errors = {}, []
    for t in tickers:
        try:
            rows = fetcher(t)
        except Exception as e:
            errors.append(f"{t}: errore scaricamento ({e})")
            continue
        if len(rows) < 260:
            errors.append(f"{t}: dati insufficienti ({len(rows)} barre)")
            continue
        data[t] = {d: p for d, p in rows}
    return data, errors


def common_dates(data):
    """Date presenti per TUTTI i ticker (periodo comune, confronto equo)."""
    if not data:
        return []
    common = None
    for series in data.values():
        ks = set(series)
        common = ks if common is None else (common & ks)
    return sorted(common, key=lambda x: int(x))


def portfolio_equity(weights, dates, data):
    """Curva del capitale con ribilanciamento annuale ai pesi target."""
    sleeves = dict(weights)  # valore di ogni "fetta", somma iniziale = 1
    eq = [1.0]
    prev_year = year_of(dates[0])
    for i in range(1, len(dates)):
        for t, w in weights.items():
            r = data[t][dates[i]] / data[t][dates[i - 1]] - 1.0
            sleeves[t] *= (1.0 + r)
        total = sum(sleeves.values())
        y = year_of(dates[i])
        if y != prev_year:  # ribilancia: riporta ai pesi target (con piccolo costo)
            total *= (1.0 - REBALANCE_COST)
            sleeves = {t: total * w for t, w in weights.items()}
            prev_year = y
        eq.append(total)
    return eq


def build_report(rows, dates, errors, today):
    L = ["# 🧺 Panieri diversificati — quanto rendono e quanto fanno soffrire",
         "",
         f"_Eseguito: {today} · ribilanciamento annuale · buy & hold_"]
    if dates:
        L.append(f"_Periodo comune analizzato: {dates[0][:10] if not dates[0].isdigit() else year_of(dates[0])} → "
                 f"{year_of(dates[-1])} ({len(dates)} giorni di mercato)_")
    L += ["",
          "> ⚠️ Non è consulenza finanziaria. Il passato non garantisce il futuro: "
          "questi anni sono stati particolari. Serve a capire il COMPROMESSO rischio/rendimento, "
          "non a promettere risultati.",
          "",
          "| Paniere | Rendimento tot. | Annuo (CAGR) | Oscillazione | Sharpe | Perdita max |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        m = r["m"]
        L.append(f"| {r['name']} | {m['total']:+.1f}% | {m['cagr']:+.1f}% | {m['vol']:.1f}% | "
                 f"{m['sharpe']:.2f} | {m['mdd']:.1f}% |")
    L += ["",
          "## Come leggerla (la colonna che conta di più è l'ultima)",
          "",
          "- **Perdita max (max drawdown)**: quanto saresti sceso dal punto più alto, nel peggiore "
          "dei casi. È il numero che ti dice se di notte dormi. Un -40% su €3.000 sono -€1.200 "
          "temporanei: se ti farebbe vendere nel panico, scegli un paniere più prudente.",
          "- **Sharpe**: rendimento per unità di rischio. Spesso i panieri diversificati hanno uno "
          "Sharpe simile o migliore del 100% azioni, pur scendendo di meno: è la magia della "
          "diversificazione (corsa più morbida a parità di qualità).",
          "- Più obbligazioni/oro → perdita max più piccola ma crescita minore. È un compromesso, "
          "non esiste il pasto gratis.",
          ""]
    if errors:
        L += ["## Ticker saltati / errori", ""]
        L += [f"- {e}" for e in errors]
        L.append("")
    return "\n".join(L)


def evaluate(portfolios, fetcher):
    data, errors = fetch_all(all_tickers(portfolios), fetcher)
    dates = common_dates(data)
    rows = []
    if len(dates) >= 260:
        for name, weights in portfolios.items():
            if all(t in data for t in weights):
                eq = portfolio_equity(weights, dates, data)
                rows.append({"name": name, "m": engine.metrics(eq)})
            else:
                errors.append(f"{name}: salto (manca qualche ticker)")
    else:
        errors.append(f"periodo comune insufficiente ({len(dates)} giorni)")
    return rows, dates, errors


def main():
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        today = "data n/d"
    print("Scarico i dati storici dei panieri (Yahoo Finance)...")
    rows, dates, errors = evaluate(PORTFOLIOS, lambda t: engine.load_yahoo(t, range_="10y"))
    report = build_report(rows, dates, errors, today)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "portfolio.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nReport salvato in: {RESULTS / 'portfolio.md'}")


if __name__ == "__main__":
    main()
