# ES4 — Verifica per Kimi Code (dopo Ernesto)

**Regola del grader cieco:** non leggere la chat o il log della sessione di Ernesto. Giudica solo i file nella cartella e gli esiti dei comandi qui sotto. Non modificare alcun file prima di aver completato tutti i controlli.

| # | Criterio | Comando / controllo | Punti |
|---|---|---|---|
| 1 | Test verdi | `cd es4 && npm run test` → exit 0 | 2 |
| 2 | Copertura | `grep -c "def test_\|it(\|test(" es4/src/lib/todos.test.js` in alternativa conta i blocchi `it(`/`test(`: ≥ 8 | 1 |
| 3 | Build verde | `cd es4 && npm run build` → exit 0 e `es4/dist/index.html` esiste | 2 |
| 4 | Persistenza corretta | `grep -r "ernesto:todos" es4/src/` presente; `loadTodos` gestisce JSON corrotto: `grep -A8 "loadTodos" es4/src/lib/todos.js` contiene try/catch o controllo equivalente | 1 |
| 5 | Purezza delle funzioni (controllo indipendente) | `node -e "import('./es4/src/lib/todos.js').then(m=>{const t=[{id:1,text:'a',done:false}];const t2=m.addTodo(t,'b');if(t2===t)throw new Error('restituisce lo stesso array');if(t.length!==1)throw new Error('muta l input');const t3=m.toggleTodo(t2,1);if(t3[0].done!==true||t2[0].done!==false)throw new Error('toggle errato');})"` → exit 0 | 2 |
| 6 | UI in italiano nel bundle | `grep -rl "Completati" es4/dist/assets/` trova file; `grep -o "<title>[^<]*" es4/dist/index.html` = `<title>Ernesto Todo` | 1 |
| 7 | Boilerplate rimosso | `! grep -ri "Learn React\|count is" es4/dist/` (nessun risultato) | 0,5 |
| 8 | Report completo | `es4/report.md` con sezioni `## Cosa ho implementato`, `## Verifica`, `## Auto-valutazione` e voto 1–10 | 0,5 |

**Totale 10.** Il criterio 5 è il decisivo tecnico: anche con test propri deboli, il controllo esterno sulle funzioni pure non si lascia ingannare. Nota: la qualità estetica (design "pulito ed elegante") NON è punteggiata in modo deterministico — se vuoi, valutala a parte servendo l'app (`npm run preview`) e facendo uno screenshot, segnandola nelle note dello scorecard come osservazione non numerica.

Esito finale da riportare: `ES4: X/10`.
