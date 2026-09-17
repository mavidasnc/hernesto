# Ernesto — Benchmark dei 3 esercizi: come si usa

## File

Per ogni esercizio ci sono tre file, da usare in ordine:

| Fase | File | Chi lo usa | Quando |
|---|---|---|---|
| 1. Fixture | `ernesto-esN-fixture.md` | Kimi Code | PRIMA: prepara la cartella `esN/` |
| 2. Prompt | `ernesto-esN-prompt.md` | Ernesto | il prompt da incollare in chat |
| 3. Verifica | `ernesto-esN-verifica.md` | Kimi Code | DOPO: grader cieco, assegna il punteggio |
| 4. Scorecard | `ernesto-scorecard.md` | Kimi Code | dopo ogni verifica, aggiorna `scorecard.csv` |

## Prerequisiti per dominio

| Esercizi | Serve |
|---|---|
| ES1–ES3 | solo Python 3.10+ |
| ES4 | Node.js ≥ 18 e npm |
| ES5 | Docker funzionante (wp-env) |

Il fixture di ES5, se Docker manca, si ferma e segnala: in quel caso salta ES5 o usalo solo su una macchina con Docker.

## Workflow per un run

1. **Fixture** — dai a Kimi Code il file fixture di ES1/ES2/ES3 (nello stesso progetto di Ernesto). Controlla che abbia eseguito solo ciò che è scritto lì.
2. **Esercizio** — avvia Ernesto (o usa `/clear`) e incolla il prompt ES-N. Il prompt dichiara un budget di chiamate a strumenti (15/20/25): se Ernesto lo supera, il task è comunque valutato sugli artefatti, ma annota il superamento nello scorecard.
3. **Verifica** — dai a Kimi Code il file verifica ES-N, in una conversazione che NON contiene la chat di Ernesto (grader cieco: si giudicano solo file ed esiti dei comandi). Kimi Code esegue i criteri a tabella e riporta `ESN: X/10`.
4. **Scorecard** — Kimi Code aggiunge la riga a `scorecard.csv` con punteggio, token, costo (da `/log` di Ernesto) e note.

## Prima di un nuovo run

Rimuovi o rinomina la cartella `esN/` del livello che vuoi ripetere: i fixture sono deterministici e ricreabili. Mai riutilizzare una cartella `esN/` già usata da un altro modello.

## Confronto tra modelli

Con due o più modelli in scorecard, confronta su:
- **punteggio** per esercizio e totale (max 30);
- **costo per punto** = `costo_usd / punteggio` (efficienza economica);
- **tool call per punto** (efficienza del loop agentico).

## Livelli

| Livello | Dominio | Skill sotto esame | Criterio decisivo |
|---|---|---|---|
| ES1 | Python | scrittura corretta + verifica con pytest | suite verde + CLI conforme (stdout/esit esatti) |
| ES2 | Python | debug + test-first + auto-valutazione | controlli funzionali esterni indipendenti dai suoi test |
| ES3 | Python | rispetto di una spec + auto-verifica | `--self-check` deve fallire su file corrotto (non una stampa finta) |
| ES4 | React/Vite | frontend + funzioni pure + persistenza | controllo esterno di purezza + build/test verdi |
| ES5 | WordPress | plugin secondo best practice + ambiente reale | REST con dati esatti dal DB di wp-env |
