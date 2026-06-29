# 🔬 Backtest del paniere — strategie a regole vs comprare e tenere

_Eseguito: 2026-06-29 00:06 UTC · costo 0.1%/operazione · long-only_

> ⚠️ Il backtest misura il PASSATO. Non garantisce il futuro. Se una strategia batte di poco il buy & hold, potrebbe essere fortuna o over-fitting.

## Riepilogo: quante volte ogni strategia batte il buy & hold

| Strategia | Batte B&H | su totale | Sharpe medio strat. | Sharpe medio B&H |
|---|---|---|---|---|
| breakout | 1 | 7 | 0.44 | 0.69 |
| rsi | 0 | 7 | 0.07 | 0.69 |
| sma | 0 | 7 | 0.33 | 0.69 |

## Dettaglio per asset

| Asset | Strategia | Ret strat. | Sharpe strat. | maxDD strat. | Ret B&H | Sharpe B&H | Op. | Esito |
|---|---|---|---|---|---|---|---|---|
| S&P 500 (SPY) | sma | +22.8% | 0.58 | -18.8% | +73.5% | 1.29 | 3 | — |
| S&P 500 (SPY) | rsi | +10.1% | 0.38 | -13.7% | +73.5% | 1.29 | 6 | — |
| S&P 500 (SPY) | breakout | +24.0% | 0.92 | -9.4% | +73.5% | 1.29 | 36 | — |
| Nasdaq 100 (QQQ) | sma | +37.6% | 0.69 | -22.8% | +97.6% | 1.23 | 3 | — |
| Nasdaq 100 (QQQ) | rsi | +15.4% | 0.50 | -15.7% | +97.6% | 1.23 | 6 | — |
| Nasdaq 100 (QQQ) | breakout | +25.0% | 0.72 | -12.8% | +97.6% | 1.23 | 42 | — |
| Oro (GLD) | sma | +69.8% | 1.00 | -26.2% | +110.3% | 1.32 | 1 | — |
| Oro (GLD) | rsi | -7.0% | -0.24 | -17.9% | +110.3% | 1.32 | 3 | — |
| Oro (GLD) | breakout | +32.7% | 0.69 | -13.9% | +110.3% | 1.32 | 38 | — |
| Bond USA (TLT) | sma | -3.4% | -0.12 | -12.7% | -4.2% | -0.03 | 6 | — |
| Bond USA (TLT) | rsi | -1.5% | -0.03 | -14.3% | -4.2% | -0.03 | 8 | — |
| Bond USA (TLT) | breakout | -7.8% | -0.32 | -19.8% | -4.2% | -0.03 | 37 | — |
| Bitcoin | sma | +38.5% | 0.40 | -37.2% | +94.5% | 0.59 | 6 | — |
| Bitcoin | rsi | +5.2% | 0.16 | -29.2% | +94.5% | 0.59 | 13 | — |
| Bitcoin | breakout | +166.3% | 1.07 | -27.5% | +94.5% | 0.59 | 38 | ✅ batte |
| Ethereum | sma | -22.0% | 0.02 | -61.7% | -15.7% | 0.20 | 6 | — |
| Ethereum | rsi | -36.1% | -0.19 | -46.6% | -15.7% | 0.20 | 13 | — |
| Ethereum | breakout | -1.7% | 0.14 | -52.6% | -15.7% | 0.20 | 46 | — |
| EUR/USD | sma | -3.8% | -0.26 | -8.9% | +4.4% | 0.23 | 4 | — |
| EUR/USD | rsi | -1.0% | -0.09 | -6.3% | +4.4% | 0.23 | 9 | — |
| EUR/USD | breakout | -1.9% | -0.12 | -7.7% | +4.4% | 0.23 | 34 | — |

## Come leggerlo

- **Sharpe** = rendimento per unità di rischio. Conta più del rendimento secco: +50% con montagne russe vale meno di +30% stabile.
- Una strategia è interessante solo se **batte il buy & hold su più asset** e regge su periodi diversi. Vincere su 1 asset solo è probabilmente caso.
- Prossimo passo se qualcosa funziona: testarla **fuori campione** (anni diversi) prima ancora di pensare ai soldi veri. Vedi `GO-LIVE.md`.