# 📊 Analista dei Mercati automatico

Il tuo **analista finanziario personale** che lavora da solo, nel cloud, anche col computer spento.
Fa due cose:

### 1. L'Analista 📰 (3 volte al giorno)
Mattina, pomeriggio e sera legge le notizie di tutti i mercati (azioni USA, Italia/Europa, crypto,
oro, valute) e ti scrive un **report completo via email**, con consigli su cosa è interessante,
a che prezzo comprare, dove mettere lo "stop" e dove vendere.

### 2. La Sentinella 🚨 (tutto il giorno)
Controlla i prezzi di continuo e, quando un'azione arriva al prezzo "giusto" segnalato dall'Analista,
**ti manda un messaggio su Telegram** all'istante.

---

## ⚠️ Da leggere prima di tutto

Questo NON è una bacchetta magica e **non garantisce guadagni**. È un assistente molto bravo che ti fa
risparmiare tempo e ti avvisa nei momenti chiave — ma le decisioni (e i soldi) restano tue. Nessuno,
né umano né computer, può prevedere i mercati con certezza. Vedi `DISCLAIMER.md`.

---

## 🔑 Cosa devi fare tu (una volta sola): le 4 "chiavi"

Sono come le chiavi di casa: servono al programma per leggere i prezzi, mandarti le email e i messaggi.
Tutte gratuite. Vanno incollate qui:
**Settings → Secrets and variables → Actions → New repository secret** (in alto a destra in questa pagina
del repository su GitHub). Per ognuna crei un "secret" con il NOME esatto indicato e incolli il valore.

| # | Nome del secret | Cos'è e dove prenderlo |
|---|---|---|
| 1 | `ANTHROPIC_API_KEY` | La chiave di Claude (l'analista). Si crea su https://console.anthropic.com → API Keys. |
| 2a | `MAIL_USERNAME` | La tua email: `matteovittorioso@gmail.com` |
| 2b | `MAIL_APP_PASSWORD` | "Password per le app" di Gmail (NON la password normale). Si crea su https://myaccount.google.com/apppasswords (serve avere la verifica in due passaggi attiva). |
| 3a | `TELEGRAM_BOT_TOKEN` | Apri Telegram, cerca **@BotFather**, scrivi `/newbot`, segui le istruzioni: ti darà un codice lungo (il token). |
| 3b | `TELEGRAM_CHAT_ID` | Su Telegram cerca **@userinfobot** e premi Start: ti dirà il tuo "Id" (un numero). Quello è il chat id. |
| 4 | `MARKET_DATA_API_KEY` | Chiave gratuita per i prezzi delle azioni: registrati su https://finnhub.io/register e copia la API key. (La crypto non ne ha bisogno.) |

> 💡 Suggerimento: dopo aver creato il bot con BotFather, **scrivigli un messaggio qualsiasi** ("ciao"),
> altrimenti Telegram non gli permette di scriverti per primo.

---

## ▶️ Come accenderlo

1. Crea le 4 chiavi qui sopra.
2. Vai su **Settings → Actions → General → Workflow permissions** e scegli **Read and write permissions**.
3. Vai sulla tab **Actions** in alto. Se vedi un avviso, clicca per **abilitare i workflow**.
4. Per provarlo subito: tab **Actions → "Market Analysis (Analista)" → Run workflow**. Dopo qualche
   minuto dovresti ricevere il primo report via email e vedere un file nuovo nella cartella `reports/`.

Da quel momento parte da solo: **mattina (~07:50), pomeriggio (~14:00) e sera (~21:30)**, ora italiana,
nei giorni feriali. La Sentinella gira invece ogni 5 minuti, tutto il giorno.

## ⏸️ Come fermarlo o metterlo in pausa

Tab **Actions → scegli il workflow → "..." (in alto a destra) → Disable workflow**. Per riaccenderlo,
stessa strada → Enable.

---

## 🛠️ Per i più curiosi: com'è fatto dentro

| Cartella / file | A cosa serve |
|---|---|
| `.github/workflows/market-analysis.yml` | Programma l'Analista 3 volte al giorno |
| `.github/workflows/sentinel.yml` | Programma la Sentinella ogni 5 minuti |
| `prompts/analyst.md` | Le istruzioni ("il cervello") dell'Analista |
| `sentinel/check.py` | Il programmino che controlla i prezzi e manda gli alert Telegram |
| `state/watchlist.json` | La lista dei prezzi da sorvegliare (la scrive l'Analista) |
| `state/fired.json` | Memoria degli alert già inviati (per non ripeterli) |
| `reports/` | L'archivio di tutti i report, giorno per giorno |

- **Dove gira:** GitHub Actions (cloud). Funziona anche col tuo PC spento.
- **Costi:** le email e gli alert sono gratis; l'Analista consuma un po' di credito della tua chiave
  Claude a ogni report (3 al giorno). Tenendo il repository **pubblico**, i minuti di GitHub Actions
  sono gratis.
- **Velocità della Sentinella:** circa 5 minuti (è il minimo di GitHub). Ottima per investimenti a
  giorni/settimane, non per operazioni al secondo.

## 💬 Parlare con l'analista (Claude Cowork)

Apri **Claude Cowork** su questo repository: l'analista avrà come contesto le sue istruzioni
(`prompts/analyst.md`), l'archivio `reports/` e la watchlist attuale, e potrai fargli domande di
approfondimento ("spiegami meglio NVIDIA", "analizza ENI", ecc.).
