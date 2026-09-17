# ernesto — analisi delle criticità e proposte di miglioramento

Data: 2026-09-17 · versione analizzata: 0.1.3 (commit `3f14f80`)

Analisi statica del codice più riproduzione dei problemi emersi nella sessione reale del
16 settembre (ricerca smartwatch e invio email con Qwen 3.8 27B). Ogni criticità riporta
l'evidenza che l'ha confermata: dove c'è un comando, è stato eseguito davvero.

> **Stato al 17 settembre 2026 (v0.2.0)**: risolte C1, C2 (documentazione più guardia con
> conferma), C3, C4, C5, C6, C8 e C9. Restano aperte **C7** (denylist aggirabile) e
> **C10** (conferme non differenziate per gravità), entrambe piccole e indipendenti.

## Sintesi

La base è solida: sandbox robusta sui tool filesystem, strumenti che non lanciano mai
eccezioni, costi e token sempre visibili, 47 test verdi. I problemi non stanno
nell'architettura ma nella **fascia di contatto con il mondo esterno**: la decodifica
dell'output dei processi, l'assenza di uno strumento per leggere pagine web e il fatto
che il costo di ogni step cresca senza alcun freno.

Due criticità sono bloccanti perché **producono silenziosamente dati sbagliati**: il
modello riceve un risultato vuoto e prosegue convinto che il comando sia andato a buon
fine. Sono C1 e, in modo più indiretto, C3.

## Criticità

### C1 — `run_command` perde l'output quando non è decodificabile (bloccante)

`ernesto/tools/shell.py:94` apre il processo con `text=True` senza specificare `encoding`,
quindi Python usa la codifica locale: su Windows `cp1252`. Qualsiasi byte non mappato (una
pagina UTF-8, l'output di `curl`, un accento in una locale diversa) solleva
`UnicodeDecodeError` **dentro il thread lettore** di `communicate()`. L'eccezione non
risale al chiamante: viene stampata sul terminale e il buffer resta vuoto.

Conseguenza: il tool restituisce `exit 0` con output vuoto. Il modello, che vede solo
`exit 0`, conclude che la pagina è vuota e riprova con altri comandi. Nella sessione del
16 settembre ha bruciato quattro step e circa 18k token di prompt per questo motivo, per
poi decidere che le pagine erano "protette da JS".

Riprodotto (l'`UnicodeDecodeError` compare nel thread e il risultato è `'exit 0\n'`):

    .venv/Scripts/python -c "
    from pathlib import Path
    from ernesto.context import load_context
    from ernesto.models import DEFAULT_MODEL
    from ernesto.session import SessionState
    from ernesto.tools.shell import RunCommandTool
    st = SessionState(model=DEFAULT_MODEL, workdir=Path('.'), context=load_context(Path('.')))
    t = RunCommandTool(st, lambda m, p=None: True)
    print(repr(t.run(command='python -c \"import sys; sys.stdout.buffer.write(bytes([0x41,0x9d,0x42]))\"')))
    "

**Fix**: `encoding="utf-8", errors="replace"` nella `Popen`. Una riga: l'output torna a
essere sempre una stringa e i byte illeggibili diventano `\ufffd` invece di far sparire
tutto il resto.

### C2 — La sandbox non vale per `run_command` (bloccante come rischio)

`resolve_in_sandbox()` protegge `read_file`, `write_file`, `edit_file` e `list_files`, ma
`run_command` esegue una shell arbitraria: la `cwd` è la workdir, però niente impedisce
`python -c "open('C:/Users/.../qualcosa','w')"` oppure `curl -o ../../fuori.txt`. La
garanzia dichiarata in README e `CLAUDE.md` (ogni path resta dentro la cartella di lavoro,
sempre, anche con `--yolo`) **vale solo per metà degli strumenti**.

Non è un difetto di implementazione ma una scelta mai dichiarata: un agente che esegue
comandi liberi non si confina senza un isolamento vero. Due sintomi concreti nei log di
questi giorni: un file di esercizio finito nella root del progetto (`x_tmp_report.md`) e
`idee.md` cancellato durante un run.

**Fix minimo**: correggere la documentazione, che oggi promette più di quanto mantenga.
**Fix reale**: eseguire i comandi in un container; in alternativa lanciare i benchmark con
`--workdir esN/`, così il raggio d'azione resta circoscritto alla cartella dell'esercizio.

### C3 — Manca uno strumento per leggere una pagina web (alta)

`brave_search` restituisce solo titolo, URL e snippet. Per leggere davvero una pagina il
modello non ha alternative a `run_command` con `curl`, e da lì va tutto storto: HTML
grezzo di decine di migliaia di caratteri, troncato a 8000 senza alcun criterio
(`TOOL_OUTPUT_LIMIT`), contenuti montati via JavaScript irraggiungibili e — finché C1 non
è risolta — output che sparisce del tutto.

**Fix**: uno strumento `fetch_url` che scarica con `httpx`, segue i redirect, rifiuta i
content-type non testuali, estrae il testo (`selectolax` o `readability`) e restituisce un
markdown pulito con un limite esplicito. È il miglioramento con il miglior rapporto
valore/costo per i task di ricerca.

### C4 — Il prompt cresce a ogni step senza alcun freno (alta)

Ogni step rispedisce l'intera storia: system prompt, tutti i messaggi e **tutti i
risultati degli strumenti**, ciascuno fino a 8000 caratteri. Nella sessione reale il
prompt è passato da 3,2k a 5,2k token in quattro step con una sola ricerca di mezzo; un
`run_command` che restituisce 8000 caratteri aggiunge ~2k token per step, pagati a ogni
chiamata successiva fino alla fine del turno. Con `MAX_AGENT_STEPS = 30` il caso peggiore
è una crescita quadratica del costo.

**Fix**: sostituire nella storia i risultati degli strumenti più vecchi di N step con un
riassunto di una riga, lasciando il contenuto integrale nel log JSONL; abbassare il limite
per gli output di `run_command`. Complementare: un comando `/compact`.

### C5 — `run_command` eredita lo stdin del terminale (media)

`Popen` non imposta `stdin`, quindi il processo figlio eredita il terminale. Un comando
che legge da stdin (`python` senza argomenti, `npm init`, un `git commit` che apre
l'editor) resta in attesa fino al timeout di 120 secondi, mentre l'utente vede l'agente
fermo senza capire perché. Il caso peggiore è un comando che consuma l'input che l'utente
stava scrivendo per il prompt successivo.

**Fix**: `stdin=subprocess.DEVNULL`. I comandi interattivi falliscono subito con un errore
leggibile (`EOFError`), che il modello sa interpretare, invece di bloccare la sessione.

### C6 — `stdout` e `stderr` sono fusi (media)

`stderr=subprocess.STDOUT` rende impossibile distinguere l'output utile dal rumore: i
warning di `npm` o `pip` finiscono mescolati ai risultati e, quando l'output viene
troncato a 8000 caratteri, può sopravvivere solo il rumore. Con `pytest` il modello fatica
a separare i fallimenti dal log di esecuzione.

**Fix**: pipe separate e output etichettato, con troncamento indipendente per ciascuno e
priorità a stdout.

### C7 — La denylist è aggirabile e dà una falsa sicurezza (media)

I pattern sono regex sul testo del comando: `rm\s+-rf` non intercetta `rm -r -f`,
`rm --recursive --force`, `RM -RF`, né uno script che fa la stessa cosa; `git\s+push` non
copre `git -C . push`.

Nessuna difesa basata su pattern testuali può essere completa: va detto esplicitamente che
la denylist protegge dalla **disattenzione**, non da un modello che voglia aggirarla. La
difesa vera è l'isolamento (C2). Miglioramenti a basso costo: match
case-insensitive e normalizzazione degli spazi prima del confronto.

### C8 — Brave: nessun retry sul limite di 1 richiesta al secondo (media)

La chiave in uso è sul piano gratuito: `x-ratelimit-policy: 1;w=1, 2000;w=2592000`. Nel
loop agentico due `brave_search` consecutive partono a pochi millisecondi di distanza e la
seconda prende `429`. Lo strumento restituisce un errore generico (`ERRORE: ricerca Brave
fallita: ...`) che il modello tende a leggere come "non ci sono risultati" invece che
"riprova tra un secondo".

**Fix**: un singolo retry dopo un secondo sul `429` e un messaggio che nomini il limite.
Inoltre gli snippet arrivano con markup HTML (`<strong>…</strong>`), rumore che entra nel
contesto a ogni ricerca: va ripulito.

### C9 — I messaggi d'errore non dicono al modello come rimediare (bassa)

`SANDBOX_ERROR` è la stringa `"ERRORE: path fuori dalla sandbox"`: non dice qual è la
cartella di lavoro né che i path vanno espressi relativi a essa. Nella sessione reale il
modello lo ha dedotto da solo ("Il sandbox non permette di scrivere in /tmp, scarico nella
cartella di lavoro"), spendendo uno step.

**Fix**: includere la workdir e l'indicazione del path relativo nel messaggio. Vale per
tutti gli errori: sono l'unico canale con cui gli strumenti insegnano al modello a usarli.

### C10 — La conferma non distingue la gravità (bassa)

`send_email` e un `rm -rf` passano dallo stesso `confirm_fn`, con la stessa domanda. Chi
conferma dieci email di seguito prende l'abitudine di premere invio, e la richiesta
davvero pericolosa arriva con lo stesso aspetto delle altre.

**Fix**: testo e default differenziati per le azioni distruttive, fino a richiedere la
digitazione del comando per i pattern più gravi.

## Miglioramenti non difensivi

- **`send_email` è solo testo**: niente HTML, destinatari multipli o allegati, mentre
  l'API Resend li supporta. Per "mandami l'elenco via mail" anche un corpo HTML minimo
  cambia molto la resa.
- **Nessuna ripresa della conversazione**: `/save` scrive in `saves/` ma non esiste il
  caricamento, quindi riprendere una sessione interrotta significa ricominciare.
- **Nessuna lista di passi interna**: sui task lunghi il modello perde il filo di ciò che
  ha già fatto; un elenco mantenuto nello stato aiuterebbe più di qualsiasi istruzione nel
  prompt.
- **`list_files` non filtra per pattern**: su progetti grandi servono un `glob` e un
  `grep`, oggi simulati con `run_command` e quindi esposti a C1 e C6.
- **Test**: buona copertura sugli strumenti, nessuna sul REPL e sui comandi slash;
  `cli.py` è il file più grande e l'unico non coperto.

## Ordine consigliato

1. **C1** — una riga, sblocca ogni uso reale di `run_command` fuori dall'ASCII.
2. **C5** e **C6** — stessa funzione e stesso test: si fanno nel passaggio di C1.
3. **C3** — `fetch_url`: è ciò che trasforma la ricerca web da dimostrazione a strumento.
4. **C2** — allineare la documentazione alla realtà, poi decidere se isolare davvero.
5. **C4** — compattazione della storia: incide sul costo di ogni sessione lunga.
6. **C8**, **C9**, **C7**, **C10** — rifiniture, tutte piccole e indipendenti fra loro.

I primi tre punti valgono mezza giornata di lavoro e cambiano la qualità percepita
dell'agente più di qualunque strumento nuovo.
