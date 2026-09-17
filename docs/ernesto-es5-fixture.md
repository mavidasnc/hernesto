# ES5 — Fixture per Kimi Code (da eseguire PRIMA di Ernesto)

**Prerequisito duro: Docker.** Verifica con `docker info` (deve funzionare senza sudo). Se Docker non c'è: fermati e segnalalo, non installare nulla — l'esercizio 5 non è avviabile su questa macchina.

1. **Struttura**: crea `es5/ernesto-stats/` e `es5/.wp-env.json` con contenuto:
   ```json
   { "plugins": ["./ernesto-stats"] }
   ```

2. **Plugin minimale** (solo per far partire l'ambiente; Ernesto lo implementerà davvero): crea `es5/ernesto-stats/ernesto-stats.php`:
   ```php
   <?php
   /**
    * Plugin Name:       Ernesto Stats
    * Description:       Statistiche articoli e commenti per mese/anno.
    * Version:           0.1.0
    * Requires at least: 6.0
    * Requires PHP:      7.4
    * Author:            Ernesto
    * Text Domain:       ernesto-stats
    */
   ```
   Verifica: `php -l es5/ernesto-stats/ernesto-stats.php` se php è disponibile localmente (altrimenti salta, wp-env lo compilerà lui).

3. **Avvia l'ambiente** (la prima volta scarica le immagini: può richiedere diversi minuti):
   ```bash
   cd es5 && npx wp-env start
   ```
   Verifica che sia su: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/wp-json/` → `200`.

4. **Pulisci il contenuto di default e crea i dati di seed** (valori attesi della verifica, annotali):
   ```bash
   npx wp-env run cli wp post delete $(npx wp-env run cli wp post list --post_status=any --format=ids) --force
   npx wp-env run cli wp comment delete $(npx wp-env run cli wp comment list --format=ids) --force
   npx wp-env run cli wp post create --post_title="Seed Marzo A" --post_status=publish --post_date="2026-03-15 10:00:00" --porcelain
   npx wp-env run cli wp post create --post_title="Seed Marzo B" --post_status=publish --post_date="2026-03-20 11:00:00" --porcelain
   npx wp-env run cli wp post create --post_title="Seed Gennaio"  --post_status=publish --post_date="2026-01-10 09:00:00" --porcelain
   npx wp-env run cli wp comment create --comment_post_id=<ID_POST_MARZO_A> --comment_content="Seed commento marzo" --comment_approved=1 --comment_date="2026-03-18 08:30:00" --porcelain
   npx wp-env run cli wp comment create --comment_post_id=<ID_POST_MARZO_A> --comment_content="Seed commento febbraio" --comment_approved=1 --comment_date="2026-02-11 19:00:00" --porcelain
   ```
   **Valori attesi per la verifica** (aggregati per anno-mese, solo post pubblicati e commenti approvati):
   - 2026-01: 1 articolo, 0 commenti
   - 2026-02: 0 articoli, 1 commento
   - 2026-03: 2 articoli, 1 commento

5. **Verifica finale del fixture**: `curl -s http://localhost:8888/wp-json/wp/v2/posts` deve mostrare 3 post datati gennaio/marzo 2026.

Non implementare REST route, pagina admin, js o css: è tutto compito di Ernesto. L'ambiente wp-env va lasciato acceso (la verifica lo usa).
