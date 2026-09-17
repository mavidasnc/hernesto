# ES4 — Fixture per Kimi Code (da eseguire PRIMA di Ernesto)

1. **Prerequisiti:** verifica che siano installati e funzionanti:
   - `node --version` → deve riportare v18 o superiore (se assente: fermati e segnala, non installare nulla);
   - `npm --version` → deve funzionare.

2. **Scaffold del progetto** nella cartella di lavoro:
   ```bash
   npm create vite@latest es4 -- --template react
   cd es4
   npm install
   npm install -D vitest
   ```

3. **Preconfigurazione:** in `es4/package.json`, aggiungi allo scripts la riga `"test": "vitest run"` (mantieni le altre). Non modificare altro.

4. **Verifica che lo scaffold sia sano** (prima di Ernesto devono già funzionare):
   - `cd es4 && npm run build` → exit 0;
   - `cd es4 && npm run test` → exit 0 o "no test files found" (vitest configurato).

Non implementare l'app dei todo, non scrivere test, non toccare `src/` oltre a quanto richiesto. Il boilerplate di default di Vite (contatore, logo) deve restare: sarà Ernesto a sostituirlo.
