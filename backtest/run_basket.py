#!/usr/bin/env python3
"""Backtest di un PANIERE diversificato su tutte le strategie a regole.

Scarica anni di storia per un paniere multi-asset (azioni, oro, bond, crypto,
forex), prova ogni strategia su ogni asset e produce un report Markdown che dice,
asset per asset, se la strategia **batte il semplice comprare e tenere** al netto
dei costi. È il modo onesto per scoprire se c'è un vantaggio PRIMA di rischiare.

Pensato per girare su GitHub Actions (trigger manuale) e mandarti il report via
email: così ottieni numeri veri senza dover programmare nulla.

  python backtest/run_basket.py            # scarica i dati e stampa/salva il report

Output: backtest/results/latest.md  (+ stampa a video).
Solo libreria standard. ⚠️ Il passato non garantisce il futuro.
"""
import os
import sys
import pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "backtest" / "results"

COST = 0.1  # % per operazione (commissioni + spread, lato singolo)

# Paniere volutamente diversificato: famiglie che non si muovono tutte insieme.
BASKET = [
    {"name": "S&P 500 (SPY)",   "source": "stooq",     "symbol": "spy.us"},
    {"name": "Nasdaq 100 (QQQ)", "source": "stooq",    "symbol": "qqq.us"},
    {"name": "Oro (GLD)",       "source": "stooq",     "symbol": "gld.us"},
    {"name": "Bond USA (TLT)",  "source": "stooq",     "symbol": "tlt.us"},
    {"name": "Bitcoin",         "source": "coingecko", "symbol": "bitcoin"},
    {"name": "Ethereum",        "source": "coingecko", "symbol": "ethereum"},
    {"name": "EUR/USD",         "source": "stooq",     "symbol": "eurusd"},
]

STRATEGIES = ["sma", "rsi", "breakout"]


def fetch(asset, days=1095):
    if asset["source"] == "stooq":
        return engine.load_stooq(asset["symbol"])
    if asset["source"] == "coingecko":
        return engine.load_coingecko(asset["symbol"], days)
    return []


def evaluate_basket(basket, strategies, cost, fetcher):
    """Ritorna (results, errors). fetcher(asset)->prezzi è iniettabile (testabile).
    results: lista di dict {asset, strategy, strat, buyhold, n_trades, beats}."""
    results, errors = [], []
    for asset in basket:
        try:
            prices = fetcher(asset)
        except Exception as e:
            errors.append(f"{asset['name']}: errore scaricamento ({e})")
            continue
        if len(prices) < 210:
            errors.append(f"{asset['name']}: dati insufficienti ({len(prices)} barre)")
            continue
        for strat in strategies:
            try:
                r = engine.evaluate(prices, strat, cost)
            except Exception as e:
                errors.append(f"{asset['name']}/{strat}: errore backtest ({e})")
                continue
            results.append({
                "asset": asset["name"], "strategy": strat,
                "strat": r["strategy"], "buyhold": r["buyhold"],
                "n_trades": r["n_trades"], "bars": r["bars"],
                "beats": r["strategy"]["sharpe"] > r["buyhold"]["sharpe"],
            })
    return results, errors


def build_report(results, errors, cost, today):
    """Costruisce il report Markdown (funzione pura, testabile offline)."""
    L = ["# 🔬 Backtest del paniere — strategie a regole vs comprare e tenere",
         "",
         f"_Eseguito: {today} · costo {cost}%/operazione · long-only_",
         "",
         "> ⚠️ Il backtest misura il PASSATO. Non garantisce il futuro. "
         "Se una strategia batte di poco il buy & hold, potrebbe essere fortuna o over-fitting.",
         ""]

    by_strat = {}
    for r in results:
        by_strat.setdefault(r["strategy"], []).append(r)

    L.append("## Riepilogo: quante volte ogni strategia batte il buy & hold")
    L.append("")
    L.append("| Strategia | Batte B&H | su totale | Sharpe medio strat. | Sharpe medio B&H |")
    L.append("|---|---|---|---|---|")
    for strat in sorted(by_strat):
        rs = by_strat[strat]
        beats = sum(1 for r in rs if r["beats"])
        avg_s = sum(r["strat"]["sharpe"] for r in rs) / len(rs)
        avg_b = sum(r["buyhold"]["sharpe"] for r in rs) / len(rs)
        L.append(f"| {strat} | {beats} | {len(rs)} | {avg_s:.2f} | {avg_b:.2f} |")
    L.append("")

    L.append("## Dettaglio per asset")
    L.append("")
    L.append("| Asset | Strategia | Ret strat. | Sharpe strat. | maxDD strat. | "
             "Ret B&H | Sharpe B&H | Op. | Esito |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        s, b = r["strat"], r["buyhold"]
        esito = "✅ batte" if r["beats"] else "—"
        L.append(f"| {r['asset']} | {r['strategy']} | {s['total']:+.1f}% | {s['sharpe']:.2f} | "
                 f"{s['mdd']:.1f}% | {b['total']:+.1f}% | {b['sharpe']:.2f} | {r['n_trades']} | {esito} |")
    L.append("")

    if errors:
        L.append("## Asset saltati / errori")
        L.append("")
        for e in errors:
            L.append(f"- {e}")
        L.append("")

    L.append("## Come leggerlo")
    L.append("")
    L.append("- **Sharpe** = rendimento per unità di rischio. Conta più del rendimento secco: "
             "+50% con montagne russe vale meno di +30% stabile.")
    L.append("- Una strategia è interessante solo se **batte il buy & hold su più asset** e regge "
             "su periodi diversi. Vincere su 1 asset solo è probabilmente caso.")
    L.append("- Prossimo passo se qualcosa funziona: testarla **fuori campione** (anni diversi) "
             "prima ancora di pensare ai soldi veri. Vedi `GO-LIVE.md`.")
    return "\n".join(L)


def main():
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        today = "data n/d"
    print("Scarico i dati storici del paniere (puo' richiedere qualche minuto)...")
    results, errors = evaluate_basket(BASKET, STRATEGIES, COST, fetch)
    report = build_report(results, errors, COST, today)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "latest.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nReport salvato in: {RESULTS / 'latest.md'}")


if __name__ == "__main__":
    main()
