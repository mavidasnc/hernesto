# Playbook — rassegna stampa

Procedura per preparare una rassegna di notizie su un tema e inviarla via email.
Leggilo solo quando Maurizio chiede una rassegna stampa.

## Passi

1. **Chiarisci il perimetro** se non è già nella richiesta: tema, arco temporale (di norma
   gli ultimi sette giorni) e numero di notizie (di norma cinque).
2. **Cerca** con `brave_search`, una query per volta e mirata. Il piano gratuito consente
   una richiesta al secondo: due ricerche di fila falliscono, quindi lavora in sequenza e
   riformula la query invece di moltiplicarla.
3. **Leggi davvero le fonti** con `fetch_url` sui risultati che sembrano rilevanti. Lo
   snippet di ricerca non basta per riassumere: dice di cosa parla la pagina, non cosa dice.
   Se una pagina non si lascia leggere, dillo e passa a un'altra fonte invece di dedurre il
   contenuto dal titolo.
4. **Scarta** i risultati promozionali, i contenuti duplicati e le pagine senza data.
5. **Scrivi la rassegna** in `rassegne/rassegna-<AAAAMMGG>.md` con questa struttura:
   - una riga di apertura con il tema e il periodo coperto;
   - per ogni notizia: titolo, fonte e data, tre o quattro righe su cosa dice e perché
     conta, link;
   - una chiusura di due o tre righe sul filo comune, se c'è. Se non c'è, dillo invece di
     inventarne uno.
6. **Invia** con `send_email` a `maurizio@mavida.com`, oggetto `Rassegna stampa — <tema>,
   <data>`, corpo uguale al file. In sessione interattiva l'invio chiede conferma.

## Regole di scrittura

- Italiano, tono professionale ma non ingessato, frasi costruite e non spezzettate.
- Niente trattini come segno di punteggiatura.
- Nessuna notizia senza fonte verificata: se non hai letto la pagina, non entra nella
  rassegna.
- Distingui sempre il fatto riportato dal commento della fonte.
