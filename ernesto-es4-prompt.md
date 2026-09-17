# ES4 — Prompt per Ernesto

Agisci con gli strumenti, minimizza il testo in chat. Hai un budget massimo di **30 chiamate a strumenti**: pianifica prima di agire.

In `es4/` trovi un progetto Vite + React già installato e funzionante (build e vitest già a posto). Trasformalo in un'app todo. Lavori solo dentro `es4/`.

1. Prima esplora lo scaffold (`package.json`, `src/`, `index.html`).
2. Crea `es4/src/lib/todos.js`: **modulo puro** (nessun import React, nessun side effect) con:
   - `createTodo(text)` → oggetto todo `{id, text, done}`;
   - `addTodo(todos, text)`, `toggleTodo(todos, id)`, `deleteTodo(todos, id)`: **funzioni pure**, restituiscono un nuovo array senza mutare l'input;
   - `FILTERS` (`all`, `active`, `done`) e `applyFilter(todos, filter)`;
   - `STORAGE_KEY = "ernesto:todos"`, `saveTodos(todos)` (serializza su localStorage) e `loadTodos()` (restituisce `[]` se la chiave manca o il JSON è corrotto — usa try/catch, mai eccezioni verso il chiamante).
3. Costruisci l'app in `src/App.jsx` (e componenti che ritieni utili): campo di input + pulsante "Aggiungi", lista con checkbox per completare e pulsante elimina per voce, filtri (Tutti / Attivi / Completati), contatore "N attività rimaste", persistenza: carica con `loadTodos()` al montaggio e salva a ogni modifica. Tutta l'UI in **italiano**.
4. **Design pulito ed elegante**: foglio CSS dedicato (es. `src/App.css`), rimuovi tutto il boilerplate di Vite (logo, contatore, "Learn React"), imposta il titolo della pagina in `index.html` a `Ernesto Todo`.
5. Crea `es4/src/lib/todos.test.js` con **almeno 8 test** vitest su: add, toggle, delete, immutabilità (l'array in input non cambia), i tre filtri, serializzazione/deserializzazione di `saveTodos`/`loadTodos` includendo il caso JSON corrotto.
6. Esegui in ordine e itera finché entrambi non danno exit 0: `npm run test` (correggi il codice, non i test) e `npm run build`.
7. Scrivi `es4/report.md` con sezioni esatte: `## Cosa ho implementato`, `## Verifica` (incolla gli output finali di test e build), `## Auto-valutazione` (voto 1–10 con 3 righe di motivazione).
8. In chat rispondi solo con: esiti di test e build, numero di iterazioni, voto che ti sei dato.
