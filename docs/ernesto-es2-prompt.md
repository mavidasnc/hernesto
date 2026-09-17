# ES2 — Prompt per Ernesto

Agisci con gli strumenti, minimizza il testo in chat. Hai un budget massimo di **20 chiamate a strumenti**: pianifica prima di agire.

In `es2/` trovi `stats.py`, un modulo di statistiche con **esattamente 3 bug logici**. Le firme delle funzioni non vanno cambiate.

1. Leggi `es2/stats.py` e scrivi `es2/test_stats.py` con **almeno 5 test** pytest che coprono media, mediana (con lista ordinata e disordinata, lunghezza pari e dispari) e moda (con frequenze pari).
2. **Prima di toccare `stats.py`**, esegui `python -m pytest es2/ -q`: almeno 3 test devono fallire. Salva l'output di questo primo run fallito (ti servirà nel report).
3. Correggi i 3 bug in `es2/stats.py`. Regola aggiuntiva per la moda: in caso di pari frequenze, restituisci il **valore minimo**.
4. Rilancia `python -m pytest es2/ -q` e itera finché non esce con codice 0.
5. Scrivi `es2/report.md` con tre sezioni esatte: `## Bug trovati` (numerati, uno per riga), `## Strategia` (spiega se hai lavorato test-first e incolla l'output del primo run fallito), `## Auto-valutazione` (voto 1–10 con 2 righe di motivazione).
6. In chat rispondi solo con: numero di bug trovati/corretti, esito finale pytest, voto che ti sei dato.
