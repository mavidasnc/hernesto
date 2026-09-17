# ES5 — Verifica per Kimi Code (dopo Ernesto)

**Regola del grader cieco:** non leggere la chat o il log della sessione di Ernesto. Giudica solo i file nella cartella e gli esiti dei comandi qui sotto. Non modificare alcun file del plugin.

Premessa: l'ambiente wp-env deve essere ancora attivo (se spento: `cd es5 && npx wp-env start`). Dati di seed attesi: 2026-01 → 1 post/0 commenti; 2026-02 → 0 post/1 commento; 2026-03 → 2 post/1 commento.

| # | Criterio | Comando / controllo | Punti |
|---|---|---|---|
| 1 | PHP valido | `find es5/ernesto-stats -name "*.php" -exec php -l {} \;` (se php locale assente: `cd es5 && npx wp-env run cli sh -c "php -l /var/www/html/wp-content/plugins/ernesto-stats/ernesto-stats.php"`) → nessun parse error | 1 |
| 2 | Attivazione pulita | `cd es5 && npx wp-env run cli wp plugin activate ernesto-stats` → exit 0 (già attivo: exit 0 con notice, vale) | 1 |
| 3 | REST corretta e dati esatti | `curl -s http://localhost:8888/wp-json/ernesto-stats/v1/monthly` → HTTP 200; poi: `python3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://localhost:8888/wp-json/ernesto-stats/v1/monthly')); m={(x['year'],x['month']):(x['posts'],x['comments']) for x in d['months']}; assert m[(2026,1)]==(1,0) and m[(2026,2)]==(0,1) and m[(2026,3)]==(2,1), m"` → exit 0 | 3 |
| 4 | Pagina admin presente e corretta | login via curl (cookie jar): `curl -s -c /tmp/es5.jar -d "log=admin&pwd=password" http://localhost:8888/wp-login.php -o /dev/null` poi `curl -s -b /tmp/es5.jar "http://localhost:8888/wp-admin/admin.php?page=ernesto-stats"` contiene `Ernesto Stats` come intestazione e `ernesto-stats-chart` (canvas o div) | 2 |
| 5 | Best practice: sicurezza e i18n | nel plugin: `grep -r "permission_callback" es5/ernesto-stats/` presente; `grep -r "current_user_can" es5/ernesto-stats/` presente; `grep -r "esc_html\|esc_attr\|esc_url" es5/ernesto-stats/` presente; `grep -r "__(" es5/ernesto-stats/` presente | 1 |
| 6 | Best practice: struttura e enqueue | file separati esistenti (`includes/rest-api.php`, `includes/admin-page.php`, `assets/admin.js`, `assets/admin.css`); `grep -r "admin_enqueue_scripts" es5/ernesto-stats/` presente; `grep -r "filemtime" es5/ernesto-stats/` presente; `uninstall.php` esiste | 1 |
| 7 | Report completo | `es5/report.md` con sezioni `## Cosa ho implementato`, `## Verifica`, `## Auto-valutazione` e voto 1–10 | 1 |

**Totale 10.** Note:
- Criterio 4: se il login via curl fallisse per problemi ambientali (redirect, cookie) dopo 2 tentativi, segnalo il criterio come "non valutabile", riscalo il punteggio su 8 e segnalo nello scorecard.
- Criterio 3 è il decisivo: dati sbagliati = il plugin non fa il suo lavoro, a prescindere da quanto è elegante il codice.
- Il rendering visivo del grafico non è punteggiato deterministicamente: se vuoi, apri la pagina admin nel browser e valuta l'aspetto come nota non numerica nello scorecard.

Esito finale da riportare: `ES5: X/10`.
