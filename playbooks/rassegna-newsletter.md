# Playbook — rassegna newsletter AI

Procedura per selezionare le novità AI dall'archivio raccolto dal progetto newsletter
(DB SQLite locale) e inviarle via email in HTML. Leggilo quando Maurizio chiede le novità
sull'AI, la rassegna della newsletter o comunque articoli dall'archivio raccolto.

La fonte non è il web: gli articoli sono già stati scaricati da `fetch_articles.py`
(progetto parallelo `newsletter`) e si leggono con il tool `newsletter_query`. Non usare
`brave_search` o `fetch_url` per questa rassegna.

## Passi

1. **Conteggio**: `newsletter_query` con `count_only=true`. Di default il tool considera
   gli articoli non processati degli ultimi 4 giorni (configurabile con `newsletter.days`
   in `context/config.yaml`). Se la richiesta indica un arco diverso ("di ieri", "dell'ultima
   settimana"), traducilo in `days`. Se il conteggio è zero, dillo e fermati.
2. **Panoramica**: `newsletter_query` con `format="table"` sullo stesso lotto: una riga per
   articolo (id, data, fonte, titolo), compatta anche con centinaia di righe. Scegli una
   shortlist di 15-20 id per titolo e fonte, scartando i contenuti promozionali e i
   duplicati evidenti.
3. **Lettura**: `newsletter_query` con `ids` (CSV di **al massimo 10 id per chiamata**) e
   `full_content=true`; per una shortlist lunga fai due chiamate invece di una.
   Valuta i contenuti e seleziona i **10 articoli** con le notizie più significative e
   importanti: annunci di laboratorio, risultati di ricerca, cambi di scenario. Se i
   candidati validi sono meno di dieci, mandali tutti senza riempire con notizie deboli.
4. **Bozza**: salva la selezione in `rassegne/rassegna-newsletter-<AAAAMMGG>.md`: una riga
   di apertura con il periodo coperto, poi per ogni articolo titolo, fonte, data, tre o
   quattro righe su cosa dice e perché conta, link.
5. **Email**: invia con `send_email` a `maurizio@mavida.com`, oggetto
   `Novità AI — <data>`. Compila sia `html` (template sotto) sia `text` (la bozza del
   punto 4 va bene). In sessione interattiva l'invio chiede conferma.
6. **Marcatura**: solo dopo l'invio riuscito, `newsletter_query` con `mark_processed=true`
   sulla **stessa selezione del lotto**: stesso `days` e **senza `ids`**. Si marcano tutti
   gli articoli valutati, non solo i dieci inviati né la shortlist: quelli scartati non
   devono ripresentarsi alla rassegna successiva. Se l'invio è stato annullato o è
   fallito, non marcare nulla.

## Template HTML

Essenziale ed elegante: contenitore da 600px centrato, font di sistema, niente immagini,
niente colonne. Struttura:

- intestazione con titolo `Novità AI` e il periodo coperto;
- per ogni articolo, un blocco con: titolo dell'articolo come link all'originale, riga meta
  con fonte e data in grigio, il riassunto in italiano (tre o quattro righe), il link
  testuale `Leggi l'approfondimento →`;
- un separatore leggero (`border-top`) tra un articolo e l'altro;
- footer di una riga con il numero di articoli e la fonte dei dati (archivio newsletter).

Usa solo CSS inline (i client di posta ignorano `<style>`), sfondo chiaro, testo scuro,
colore di accento unico per i link.

## Regole di scrittura

- Italiano, tono professionale ma non ingessato, frasi costruite e non spezzettate.
- Niente trattini come segno di punteggiatura.
- Riassumi solo articoli che hai letto: il titolo da solo non basta.
- Distingui sempre il fatto riportato dal commento della fonte.
