# ES3 — Fixture per Kimi Code (da eseguire PRIMA di Ernesto)

1. Crea la cartella `es3/` (se non esiste) e il file `es3/vendite.csv` con ESATTAMENTE questo contenuto:

```csv
categoria,prodotto,pezzi,prezzo
frutta,mela,10,0.50
frutta,pera,5,0.80
verdura,spinaci,3,1.20
frutta,banana,8,0.30
verdura,broccoli,4,1.50
frutta,mela,7,0.50
```

2. Conferma che il CSV sia valido e calcola tu i valori attesi (servono alla verifica finale):

```bash
python -c "
import csv
righe = list(csv.DictReader(open('es3/vendite.csv')))
cat = {}
for r in righe:
    c = cat.setdefault(r['categoria'], [0, 0.0])
    c[0] += int(r['pezzi']); c[1] += int(r['pezzi']) * float(r['prezzo'])
for k, (p, f) in sorted(cat.items(), key=lambda kv: -kv[1][1]):
    print(f'{k}: {p} pezzi, {f:.2f} EUR')
print(f'TOTALE: {sum(p for p,_ in cat.values())} pezzi, {sum(f for _,f in cat.values()):.2f} EUR')"
```

Output atteso:
```
frutta: 30 pezzi, 14.90 EUR
verdura: 7 pezzi, 9.60 EUR
TOTALE: 37 pezzi, 24.50 EUR
```

Se l'output non corrisponde, il fixture è sbagliato: correggilo prima di procedere (mai toccarlo dopo che Ernesto ha iniziato).

Non scrivere codice al posto di Ernesto, non aggiungere altri file.
