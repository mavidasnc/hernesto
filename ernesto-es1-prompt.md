# ES1 — Prompt per Ernesto

Agisci con gli strumenti, minimizza il testo in chat. Hai un budget massimo di **15 chiamate a strumenti**: pianifica prima di agire.

1. Verifica con `list_files` il contenuto di `es1/` (dovrebbe esistere ed essere vuota) e lavora solo lì dentro.
2. Crea `es1/fizzbuzz.py` con:
   - funzione `fizzbuzz(n: int) -> str`: multipli di 3 → `"Fizz"`, di 5 → `"Buzz"`, di entrambi → `"FizzBuzz"`, altrimenti la stringa del numero;
   - CLI: `python es1/fizzbuzz.py 15` stampa solo il risultato per quel numero; senza argomenti stampa i risultati da 1 a 100, uno per riga;
   - con argomento non numerico: messaggio d'errore su **stderr** ed exit code **2**.
3. Crea `es1/test_fizzbuzz.py` con **almeno 6 test** pytest che coprono: 3, 5, 15, 7 (caso neutro), 1, 90.
4. Esegui `python -m pytest es1/ -q` e **itera finché non esce con codice 0**. Se un test fallisce, correggi il codice (non il test) e rilancia.
5. Scrivi `es1/report.md` con tre sezioni esatte: `## Cosa ho implementato`, `## Verifica` (incolla l'output finale di pytest), `## Auto-valutazione` (voto 1–10 e 2 righe di motivazione).
6. In chat rispondi solo con: esito pytest finale (pass/fail), numero di iterazioni fatte, voto che ti sei dato.
