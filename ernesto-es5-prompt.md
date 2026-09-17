# ES5 — Prompt per Ernesto

Agisci con gli strumenti, minimizza il testo in chat. Hai un budget massimo di **35 chiamate a strumenti**: pianifica prima di agire.

In `es5/` trovi un ambiente WordPress locale già avviato con `wp-env` (sito: `http://localhost:8888`, admin: `admin` / `password`) e lo scheletro del plugin `es5/ernesto-stats/`. Implementa il plugin completo seguendo le best practice WordPress. Lavori solo dentro `es5/`.

1. **Esplora prima**: leggi lo scheletro del plugin e verifica l'ambiente (`curl http://localhost:8888/wp-json/`).
2. **REST API**: registra la route `GET /wp-json/ernesto-stats/v1/monthly` che restituisce JSON:
   ```json
   {"months": [{"year": 2026, "month": 1, "posts": 1, "comments": 0}]}
   ```
   - aggregazione per anno-mese su TUTTO l'arco temporale, solo post con `post_status = publish` e commenti approvati;
   - solo i mesi che hanno almeno un articolo o un commento, ordinati cronologicamente;
   - query con `$wpdb` prepared o API WordPress, mai SQL concatenato;
   - `permission_callback` esplicita (lettura pubblica).
3. **Pagina di amministrazione**: sotto **Strumenti → Ernesto Stats** (slug `ernesto-stats`, capability `manage_options`):
   - intestazione `<h1>Ernesto Stats</h1>`;
   - un `<canvas id="ernesto-stats-chart">` (o div equivalente) con **grafico a barre** articoli e commenti per mese;
   - un selettore `<select>` per filtrare per anno;
   - i dati arrivano via `fetch()` dalla tua REST route;
   - per il grafico puoi usare Chart.js da CDN (enqueue corretto) o disegnare tu sul canvas: a tua scelta, **nessun build step** (JS vanilla).
4. **Struttura dei file** (separa le responsabilità):
   ```
   ernesto-stats/
     ernesto-stats.php      # bootstrap, constants, activation
     includes/rest-api.php  # route REST
     includes/admin-page.php# menu, enqueue, markup
     assets/admin.js
     assets/admin.css
   ```
5. **Best practice obbligatorie**: escaping in output (`esc_html`, `esc_url`, `esc_attr`), text domain `ernesto-stats` con funzioni di traduzione, script enqueueati su `admin_enqueue_scripts` con `filemtime` come versione, niente variabili globali, prefisso `ernesto_stats_` per hook/funzioni/opzioni, `uninstall.php` che pulisce quanto creato.
6. **Verifica iterativa via wp-env** (fino a esito positivo):
   - `npx wp-env run cli wp plugin activate ernesto-stats` → exit 0;
   - `curl -s http://localhost:8888/wp-json/ernesto-stats/v1/monthly` → JSON con, tra gli altri: 2026-01 → 1 post / 0 commenti; 2026-02 → 0 post / 1 commento; 2026-03 → 2 post / 1 commento (i totali vanno calcolati dal DB, mai hardcodati);
   - se qualcosa fallisce, leggi l'errore (log PHP: `npx wp-env run cli wp eval 'error_log(...)'` o `npx wp-env logs`) e correggi.
7. Scrivi `es5/report.md` con sezioni esatte: `## Cosa ho implementato`, `## Verifica` (incolla output di attivazione e della REST), `## Auto-valutazione` (voto 1–10 con 3 righe di motivazione).
8. In chat rispondi solo con: esito attivazione, JSON della REST (troncato ai 3 mesi), voto che ti sei dato.
