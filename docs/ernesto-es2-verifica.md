# ES2 — Verifica per Kimi Code (dopo Ernesto)

**Regola del grader cieco:** non leggere la chat o il log della sessione di Ernesto. Giudica solo i file nella cartella e gli esiti dei comandi qui sotto. Non modificare alcun file prima di aver completato tutti i controlli.

I 3 bug originali erano: (1) media che divide per `len(numeri)+1`; (2) mediana che non ordina la lista; (3) moda che con frequenze pari non restituisce il minimo.

| # | Criterio | Comando / controllo | Punti |
|---|---|---|---|
| 1 | Test esistenti e sufficienti | `grep -c "def test_" es2/test_stats.py` ≥ 5 | 1 |
| 2 | Prova di test-first | `es2/report.md`, sezione `## Strategia` contiene un output pytest con almeno 3 `FAILED` | 2 |
| 3 | Suite verde | `python -m pytest es2/ -q` exit 0 | 2 |
| 4 | Correttezza funzionale (controlli indipendenti dai test di Ernesto) | `python -c "import sys; sys.path.insert(0,'es2'); from stats import media, mediana, moda; assert media([1,2,3])==2.0; assert media([2,2,2,2])==2.0; assert mediana([3,1,2])==2; assert mediana([4,1,2,3])==2.5; assert moda([1,2,2,3,3])==2"` exit 0 | 3 |
| 5 | Bug identificati correttamente | `es2/report.md`, sezione `## Bug trovati` elenca 3 bug coerenti con (1)(2)(3) | 1 |
| 6 | Firme invariate | `stats.py` mantiene le firme `media(numeri: list[float]) -> float`, `mediana(numeri: list[float]) -> float`, `moda(numeri: list[int]) -> int` | 0,5 |
| 7 | Report completo | sezioni `## Bug trovati`, `## Strategia`, `## Auto-valutazione` presenti, con voto 1–10 | 0,5 |

**Totale 10.** Il criterio 4 è decisivo: anche con test propri sbagliati ma verdi, i controlli esterni non si lasciano ingannare. Se il criterio 2 fallisce (nessun output con FAILED nel report) ma tutto il resto è corretto, annota nello scorecard "test-first non documentato".

Esito finale da riportare: `ES2: X/10`.
