# Ernesto — Scorecard del benchmark

Dopo OGNI verifica, aggiorna il file `scorecard.csv` nella cartella del progetto: **aggiungi una riga, non modificare mai le righe passate**.

## Struttura del file

Se `scorecard.csv` non esiste, crealo con questa intestazione:

```csv
data,modello,esercizio,punteggio,massimo,token_in,token_out,costo_usd,tool_call,note
```

## Colonne

| Colonna | Valore |
|---|---|
| `data` | data della sessione, formato `YYYY-MM-DD` |
| `modello` | id OpenRouter del modello attivo su Ernesto (es. `qwen/qwen3.8-27b`) — rilevabile con `/context` |
| `esercizio` | `ES1`, `ES2` o `ES3` |
| `punteggio` | X assegnato dalla verifica |
| `massimo` | sempre `10` |
| `token_in`, `token_out` | cumulativi di sessione rilevabili con `/log` |
| `costo_usd` | cumulativo di sessione da `/log` |
| `tool_call` | numero di chiamate a strumenti usate (dal log JSONL di Ernesto; se non disponibile, lascia vuoto) |
| `note` | osservazioni: iterazioni, test modificati, test-first non documentato, step budget superato, ecc. — senza virgole (usare `;` al loro interno) |

## Riga di esempio

```csv
2026-09-16,qwen/qwen3.8-27b,ES2,8,10,45210,12300,0.0321,17,bug 2 individuato ma descritto vagamente; test-first documentato
```

## Regole

1. Un confronto tra modelli è valido solo a parità di esercizio e fixture: prima di un nuovo run, cancella o rinomina la cartella `esN/` (i fixture sono riproducibili dai rispettivi file).
2. Se lo stesso modello ripete un esercizio, aggiungi una nuova riga: lo storico conta.
3. Confronta i modelli su tre assi: punteggio, costo per punto (`costo_usd / punteggio`), e tool_call per punto (efficienza del loop).
