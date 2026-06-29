# 🚦 Prima di usare soldi veri — leggimi due volte

> ⚠️ Questo file non è consulenza finanziaria. È una checklist di buon senso scritta
> per proteggere i tuoi risparmi da decisioni prese con l'entusiasmo invece che coi dati.

## La verità in una riga

**Costruire bene il software non fa guadagnare. Serve solo a scoprire *se* esiste un
vantaggio, prima di rischiare.** Nessun bot, AI o persona può prevedere i mercati con
certezza. L'obiettivo realistico non è "indovinare il futuro": è avere un piccolo
vantaggio statistico e **sopravvivere** abbastanza a lungo perché si manifesti.

## Il problema di fondo del bot attuale

La strategia odierna — *l'AI legge le news 3 volte al giorno e sceglie* — **non è
testabile sul passato**: non puoi rigiocare le notizie storiche dentro un'AI. Quindi
oggi **non abbiamo alcuna prova** che abbia un vantaggio. Reagire alle news, per giunta,
è uno dei modi più studiati per perdere soldi al dettaglio (quando la notizia arriva a
te, è già nel prezzo).

Per questo gli strumenti che trovi qui sotto puntano su strategie **a regole**, che si
possono validare con un backtest. Finché non hai una di quelle con un vantaggio provato
(o mesi di paper trading con numeri solidi), i soldi veri sono una scommessa.

## ✅ Checklist da superare PRIMA di mettere un euro

Non passare al denaro reale finché **tutte** queste caselle non sono spuntate:

- [ ] **Storico paper trading ≥ 3-6 mesi** e **≥ 30-50 operazioni chiuse** (sotto è rumore).
- [ ] `python risk/performance.py` mostra **Sharpe > 1** e **max drawdown** che riesci a
      sopportare emotivamente (se -20% ti fa vendere nel panico, la strategia non fa per te).
- [ ] Esiste **almeno una strategia a regole** che nel backtest **batte il buy & hold**
      al netto dei costi (`python backtest/engine.py ...`), su più asset e più periodi.
- [ ] I risultati reggono **fuori campione** (testato su anni diversi da quelli usati per
      scegliere i parametri) — altrimenti è solo over-fitting.
- [ ] Hai deciso in anticipo **quanto puoi perdere in totale** e a quale perdita stacchi tutto.
- [ ] I costi reali del tuo broker (commissioni + spread) sono ≤ a quelli simulati
      (`round_trip_cost_pct`, oggi 0,2%).

## 💶 Quanto rischiare (se proprio parti)

- **Mai** partire con tutti i €2-3.000. Inizia con una cifra che, se sparisse domani,
  non cambierebbe la tua vita — es. **€200-300**. Aumenti solo dopo mesi di risultati reali.
- **Rischio per operazione ≤ 1%** del capitale (con €300 = €3 di perdita massima per trade,
  decisa dalla distanza dello stop, non dall'importo investito).
- Tieni i soldi del "gioco" **separati** da quelli che ti servono per vivere.

## 🆓 Cosa ho già aggiunto (gratis, zero chiavi nuove)

| Strumento | Cosa fa | Come si usa |
|---|---|---|
| Freno anti-concentrazione | Blocca aperture troppo sbilanciate (max 1 per categoria, ≤35%) | automatico nella Sentinella |
| Prezzi multi-asset | Crypto (CoinGecko) + forex (Frankfurter) + azioni/ETF (Finnhub) | automatico |
| Costi realistici | Ogni operazione paga commissioni+spread simulati (0,2%) | `round_trip_cost_pct` in `check.py` |
| Circuit breaker | Sospende le nuove aperture se il capitale cade oltre -20% dal picco | automatico |
| Storico capitale | Una riga al giorno in `state/equity_history.csv` | automatico |
| Cruscotto metriche | Sharpe, Sortino, drawdown, win rate, profit factor | `python risk/performance.py` |
| Motore di backtest | Testa strategie a regole sul passato vs buy & hold | `python backtest/engine.py --help` |

## 💰 Opzioni a pagamento — cosa servono DAVVERO (e cosa no)

Te le metto in ordine di utilità reale. **Nessuna ti garantisce guadagni**: comprano
affidabilità e capacità di validare, non una sfera di cristallo.

| Spesa | Costo indicativo | Serve? | Cosa compri |
|---|---|---|---|
| **Dati storici/intraday di qualità** (Twelve Data, Polygon, EOD) | ~$30-100/mese | **Sì, per prima** | Backtest affidabili e prezzi al minuto. È l'unica spesa che migliora *davvero* la validazione. |
| Forex/commodity intraday (oggi via Frankfurter è ~1 volta/giorno) | incluso sopra | Solo se fai intraday | Tassi al minuto invece che giornalieri |
| Più credito API Claude | pochi $/mese | Opzionale | Analisi più frequenti — **non** capacità predittiva |
| Hosting/compute dedicato | ~$5-10/mese | No, per ora | GitHub Actions gratis basta abbondantemente |
| Broker con API per esecuzione reale | commissioni per trade | Solo a validazione fatta | Passare dal paper ai soldi veri |

**Il mio consiglio da amico:** finché la checklist qui sopra non è verde, **spesa = 0**.
La prima (ed eventualmente unica) spesa sensata sono i **dati storici** per fare backtest
seri. Tutto il resto è ottimizzare un motore che non sappiamo ancora se ha benzina.

## La cosa più onesta che posso dirti

L'esito più probabile, per chiunque parta col trading sistematico al dettaglio, è
**perdere soldi**. Le persone che ci guadagnano in modo costante sono pochissime, hanno
strumenti che noi non abbiamo, e si accontentano di vantaggi piccoli ben gestiti. Se
affronti questa cosa come un esperimento da cui imparare — con soldi che puoi perdere —
può essere istruttiva e persino divertente. Se la affronti come "la macchina da soldi
che mi cambia la vita", ti farà male. Ti voglio dalla prima parte.
