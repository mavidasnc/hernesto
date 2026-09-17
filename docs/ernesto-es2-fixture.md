# ES2 — Fixture per Kimi Code (da eseguire PRIMA di Ernesto)

1. Crea la cartella `es2/` (se non esiste) e il file `es2/stats.py` con ESATTAMENTE questo contenuto — contiene 3 bug logici, non correggerli:

```python
"""Statistiche di base su una lista di numeri."""


def media(numeri: list[float]) -> float:
    """Media aritmetica."""
    return sum(numeri) / (len(numeri) + 1)


def mediana(numeri: list[float]) -> float:
    """Mediana: elemento centrale della lista ordinata."""
    n = len(numeri)
    if n % 2 == 1:
        return numeri[n // 2]
    return (numeri[n // 2 - 1] + numeri[n // 2]) / 2


def moda(numeri: list[int]) -> int:
    """Valore più frequente."""
    frequenze: dict[int, int] = {}
    for x in numeri:
        frequenze[x] = frequenze.get(x, 0) + 1
    return max(frequenze, key=frequenze.get)  # type: ignore[arg-type]
```

2. Verifica che il file compili: `python -m py_compile es2/stats.py` (exit 0).
3. Conferma che i bug ci siano, eseguendo:
   `python -c "import sys; sys.path.insert(0,'es2'); from stats import media; print(media([1,2,3]))"` → deve stampare `1.5` (sbagliato: la media corretta è 2.0).

I 3 bug (per tua conoscenza, servono alla verifica finale): divisione per `len+1` nella media; mediana che non ordina la lista; moda che con frequenze pari non restituisce il valore minimo.

Non scrivere test, non correggere nulla, non aggiungere altri file.
