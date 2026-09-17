# ES1 — Verifica per Kimi Code (dopo Ernesto)

**Regola del grader cieco:** non leggere la chat o il log della sessione di Ernesto. Giudica solo i file nella cartella e gli esiti dei comandi qui sotto. Non modificare alcun file prima di aver completato tutti i controlli.

| # | Criterio | Comando / controllo | Punti |
|---|---|---|---|
| 1 | File presenti | `ls es1/fizzbuzz.py es1/test_fizzbuzz.py es1/report.md` exit 0 | 1 |
| 2 | Test verdi | `python -m pytest es1/ -q` exit 0 | 3 |
| 3 | Copertura minima | `grep -c "def test_" es1/test_fizzbuzz.py` ≥ 6 | 1 |
| 4 | CLI singolo numero | `python es1/fizzbuzz.py 15` → stdout esattamente `FizzBuzz` | 1 |
| 5 | CLI range | `python es1/fizzbuzz.py` → 100 righe; riga 15 = `FizzBuzz`; riga 7 = `7` | 1 |
| 6 | Gestione errore | `python es1/fizzbuzz.py abc` → exit **2** e stderr non vuoto | 2 |
| 7 | Report completo | `es1/report.md` contiene le sezioni `## Cosa ho implementato`, `## Verifica`, `## Auto-valutazione` e un voto 1–10 | 1 |

**Totale 10.** Se Ernesto ha modificato i propri test dopo il primo run per farli passare, annotalo nelle note dello scorecard ma non penalizzare (al livello 1 conta l'iterazione).

Esito finale da riportare: `ES1: X/10`.
