# ES3 — Verifica per Kimi Code (dopo Ernesto)

**Regola del grader cieco:** non leggere la chat o il log della sessione di Ernesto. Giudica solo i file nella cartella e gli esiti dei comandi qui sotto. Non modificare alcun file prima di aver completato tutti i controlli, tranne dove indicato nel criterio 4 (corruzione di prova).

Valori attesi (dal fixture): frutta 30 pezzi / 14.90 EUR, verdura 7 pezzi / 9.60 EUR, TOTALE 37 pezzi / 24.50 EUR.

| # | Criterio | Comando / controllo | Punti |
|---|---|---|---|
| 1 | File presenti | `ls es3/report.py es3/report.md es3/vendite.csv es3/test_report.py` exit 0 | 1 |
| 2 | Stdout esatto | `python es3/report.py` → stdout esattamente `OK 24.50` | 2 |
| 3 | Report corretto | `es3/report.md` contiene: riga frutta con `30` e `14.90`, riga verdura con `7` e `9.60`, riga `TOTALE: 37 pezzi, 24.50 EUR`, frutta elencata **prima** di verdura (fatturato decrescente) | 2 |
| 4 | Self-check reale | a) `python es3/report.py --self-check` → `CHECK PASS`, exit 0. b) Modifica **un solo numero** in `es3/report.md` (es. cambia 24.50 in 99.50), rilancia `--self-check` → deve stampare `CHECK FAIL` ed exit 1. c) Rilancia `python es3/report.py` per rigenerare il file pulito e verifica che il criterio 3 valga ancora | 2 |
| 5 | Solo stdlib | `python -c "import ast; tree=ast.parse(open('es3/report.py').read()); mods={n.names[0].name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}|{(n.module or '').split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}; std={'csv','json','sys','os','pathlib','collections','dataclasses','argparse','typing','io','functools','itertools','math','re','datetime','tempfile','shutil'}; assert mods<=std, mods"` exit 0 | 1 |
| 6 | Test minimi | `python -m pytest es3/ -q` exit 0 con ≥3 test | 1 |
| 7 | Auto-valutazione | sezione `## Auto-valutazione` in `es3/report.md` con voto e checklist ✓/✗ dei vincoli | 1 |

**Totale 10.** Il criterio 4 misura la capacità di auto-verifica vera: il `CHECK FAIL` su file corrotto smaschera un self-check finto (una stampa hardcoded darebbe sempre PASS). Se il self-check fallisce la prova di corruzione, assegna 0 al criterio 4 indipendentemente dal PASS iniziale.

Esito finale da riportare: `ES3: X/10`.
