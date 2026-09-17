# ES3 — Prompt per Ernesto

Agisci con gli strumenti, minimizza il testo in chat. Hai un budget massimo di **25 chiamate a strumenti**: pianifica prima di agire.

In `es3/` trovi `vendite.csv` con colonne `categoria,prodotto,pezzi,prezzo`. Lavori solo in `es3/`.

1. Leggi `es3/vendite.csv` per capire i dati (non hardcodare i totali nel codice: devono essere calcolati dal CSV a ogni esecuzione).
2. Scrivi `es3/report.py` rispettando TUTTI questi vincoli:
   - **solo standard library**, e solo moduli essenziali (`csv`, `sys`, `pathlib`, `argparse`, `collections`, ...): nessuna dipendenza esterna, nessun `pip install`, nessun import superfluo — **evita anche `from __future__ import annotations`**;
   - si esegue con `python es3/report.py` (nessun argomento) e deve:
     a. leggere `vendite.csv` con il modulo `csv`;
     b. scrivere `es3/report.md` con una tabella markdown: per ogni categoria `totale pezzi` e `fatturato` (2 cifre decimali), categorie in ordine di fatturato decrescente; in fondo la riga `TOTALE: <pezzi> pezzi, <fatturato> EUR`;
     c. stampare su stdout **esattamente** `OK <fatturato totale con 2 cifre decimali>`;
   - supporta il flag `--self-check`: rigenera il report in memoria e confronta ogni valore con quello scritto su disco e con i valori ricalcolati da zero; se tutto coincide stampa `CHECK PASS` ed esce 0, altrimenti `CHECK FAIL` ed esce 1.
3. Scrivi `es3/test_report.py` con almeno 3 test pytest (usa `tmp_path` per non sporcare il disco: copia il CSV in una directory temporanea).
4. Esegui in ordine e itera finché tutti non danno esito 0: `python es3/report.py`, poi `python es3/report.py --self-check`, poi `python -m pytest es3/ -q`.
5. Aggiungi in fondo a `es3/report.md` la sezione `## Auto-valutazione`: voto 1–10, 3 righe di motivazione, e l'elenco dei vincoli con accanto ✓/✗. **Attenzione**: ogni esecuzione di `report.py` rigenera `report.md` da zero — la sezione deve essere presente nel file FINALE, quindi aggiungila solo dopo l'ultima esecuzione oppure fai in modo che `report.py` la preservi.
6. In chat rispondi solo con: output dei tre comandi, voto che ti sei dato.
