# 🔬 Backtest del paniere — strategie a regole vs comprare e tenere

_Eseguito: 2026-06-29 00:04 UTC · costo 0.1%/operazione · long-only_

> ⚠️ Il backtest misura il PASSATO. Non garantisce il futuro. Se una strategia batte di poco il buy & hold, potrebbe essere fortuna o over-fitting.

## Riepilogo: quante volte ogni strategia batte il buy & hold

| Strategia | Batte B&H | su totale | Sharpe medio strat. | Sharpe medio B&H |
|---|---|---|---|---|

## Dettaglio per asset

| Asset | Strategia | Ret strat. | Sharpe strat. | maxDD strat. | Ret B&H | Sharpe B&H | Op. | Esito |
|---|---|---|---|---|---|---|---|---|

## Asset saltati / errori

- S&P 500 (SPY): dati insufficienti (0 barre)
- Nasdaq 100 (QQQ): dati insufficienti (0 barre)
- Oro (GLD): dati insufficienti (0 barre)
- Bond USA (TLT): dati insufficienti (0 barre)
- Bitcoin: errore scaricamento (HTTP Error 401: Unauthorized)
- Ethereum: errore scaricamento (HTTP Error 401: Unauthorized)
- EUR/USD: dati insufficienti (0 barre)

## Come leggerlo

- **Sharpe** = rendimento per unità di rischio. Conta più del rendimento secco: +50% con montagne russe vale meno di +30% stabile.
- Una strategia è interessante solo se **batte il buy & hold su più asset** e regge su periodi diversi. Vincere su 1 asset solo è probabilmente caso.
- Prossimo passo se qualcosa funziona: testarla **fuori campione** (anni diversi) prima ancora di pensare ai soldi veri. Vedi `GO-LIVE.md`.