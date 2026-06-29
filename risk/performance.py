#!/usr/bin/env python3
"""Cruscotto di performance del portafoglio simulato.

Legge lo storico del capitale (state/equity_history.csv) e le operazioni chiuse
(state/portfolio.json) e calcola le metriche che dicono *davvero* se la strategia
funziona — non solo il guadagno, ma il guadagno **aggiustato per il rischio**:

  - Rendimento totale e annualizzato (CAGR)
  - Volatilità annualizzata
  - Sharpe ratio (rendimento per unità di rischio) e Sortino (solo rischio al ribasso)
  - Max drawdown (la peggior caduta dal picco) e drawdown attuale
  - Statistiche per operazione: win rate, profit factor, expectancy, vincita/perdita media

Senza queste metriche "sta andando bene?" è una domanda senza risposta: 2 trade
fortunati e una strategia perdente possono sembrare identici. Solo libreria standard.

⚠️ Simulazione: soldi finti. Non è consulenza finanziaria.
"""
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORTFOLIO = ROOT / "state" / "portfolio.json"
EQUITY_HISTORY = ROOT / "state" / "equity_history.csv"

TRADING_DAYS = 252  # giorni di mercato in un anno, per annualizzare


def read_equity_curve():
    """Restituisce la lista (date, equity) dallo storico CSV, in ordine."""
    if not EQUITY_HISTORY.exists():
        return []
    out = []
    for i, line in enumerate(EQUITY_HISTORY.read_text(encoding="utf-8").splitlines()):
        if i == 0 or not line.strip():
            continue  # header
        parts = line.split(",")
        try:
            out.append((parts[0], float(parts[1])))
        except (IndexError, ValueError):
            continue
    return out


def daily_returns(equity):
    out = []
    for a, b in zip(equity, equity[1:]):
        if a:
            out.append(b / a - 1.0)
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def max_drawdown(equity):
    """Max drawdown (frazione negativa) e drawdown corrente dalla curva equity."""
    peak = equity[0] if equity else 0.0
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak:
            mdd = min(mdd, v / peak - 1.0)
    cur = (equity[-1] / peak - 1.0) if (equity and peak) else 0.0
    return mdd, cur


def trade_stats(closed):
    pnls = [t.get("pnl", 0.0) for t in closed]
    wins = [p for p in pnls if p >= 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": len(pnls),
        "win_rate": (len(wins) / len(pnls) * 100.0) if pnls else 0.0,
        "avg_win": mean(wins),
        "avg_loss": mean(losses),
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf") if gross_win else 0.0,
        "expectancy": mean(pnls),
        "best": max(pnls) if pnls else 0.0,
        "worst": min(pnls) if pnls else 0.0,
    }


def main():
    p = json.loads(PORTFOLIO.read_text(encoding="utf-8")) if PORTFOLIO.exists() else {}
    cfg = p.get("config", {})
    start = cfg.get("starting_capital", 1000.0)
    closed = p.get("closed_trades", [])

    curve = read_equity_curve()
    eq = [v for _, v in curve]

    L = []
    L.append("=== CRUSCOTTO PERFORMANCE (simulazione, soldi finti) ===")
    L.append("")

    if len(eq) < 2:
        L.append(f"Storico capitale: {len(eq)} punto/i — troppo pochi per le metriche di rischio.")
        L.append("La curva equity si popola di un punto al giorno (bilancio serale).")
        L.append("Servono settimane/mesi di storico prima di trarre conclusioni affidabili.")
    else:
        rets = daily_returns(eq)
        total_ret = (eq[-1] / eq[0] - 1.0) * 100.0
        vol_ann = stdev(rets) * math.sqrt(TRADING_DAYS) * 100.0
        cagr = ((eq[-1] / eq[0]) ** (TRADING_DAYS / len(rets)) - 1.0) * 100.0 if eq[0] else 0.0
        sharpe = (mean(rets) / stdev(rets) * math.sqrt(TRADING_DAYS)) if stdev(rets) else 0.0
        downside = stdev([r for r in rets if r < 0])
        sortino = (mean(rets) / downside * math.sqrt(TRADING_DAYS)) if downside else 0.0
        mdd, cur_dd = max_drawdown(eq)

        L.append(f"Punti storici (giorni): {len(eq)}  |  capitale {eq[0]:,.2f} -> {eq[-1]:,.2f}")
        L.append(f"Rendimento totale:        {total_ret:+.2f}%")
        L.append(f"Rendimento annualizz.:    {cagr:+.2f}%  (CAGR, proiezione su base storica breve)")
        L.append(f"Volatilita annualizz.:    {vol_ann:.2f}%")
        L.append(f"Sharpe ratio:             {sharpe:.2f}   (>1 buono, >2 ottimo; rf=0)")
        L.append(f"Sortino ratio:            {sortino:.2f}   (come Sharpe ma solo rischio al ribasso)")
        L.append(f"Max drawdown:             {mdd * 100:.2f}%  (peggior caduta dal picco)")
        L.append(f"Drawdown attuale:         {cur_dd * 100:.2f}%")

    L.append("")
    L.append("OPERAZIONI CHIUSE:")
    ts = trade_stats(closed)
    if ts["n"] == 0:
        L.append("- Nessuna operazione chiusa: niente statistiche per-trade.")
    else:
        pf = ts["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        L.append(f"- Operazioni: {ts['n']}  |  win rate: {ts['win_rate']:.1f}%")
        L.append(f"- Vincita media: {ts['avg_win']:+,.2f}  |  perdita media: {ts['avg_loss']:+,.2f}")
        L.append(f"- Profit factor: {pf_s}  (somma vincite / somma perdite; >1 = in utile)")
        L.append(f"- Expectancy:    {ts['expectancy']:+,.2f} per operazione  (atteso medio)")
        L.append(f"- Migliore: {ts['best']:+,.2f}  |  peggiore: {ts['worst']:+,.2f}")

    L.append("")
    L.append("Nota: con poche operazioni o storico breve questi numeri sono rumore.")
    L.append("Regola pratica: nessuna conclusione sotto ~30-50 operazioni chiuse.")
    print("\n".join(L))


if __name__ == "__main__":
    main()
