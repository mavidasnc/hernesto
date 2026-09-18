# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/),
e il progetto aderisce al [Versionamento Semantico](https://semver.org/lang/it/).

## [0.17.0] - 2026-09-18

### Aggiunto
- **`search_files`**: ricerca testuale o regex nei file della cartella di lavoro, con output `percorso:riga: testo`, saltando binari e cartelle generate. Prima il modello doveva cercare con `run_command` e grep, fuori dalle garanzie della sandbox. Idea presa da context-mode (cerca invece di riversare i file nel contesto), in forma proporzionata ai pochi MB di markdown di ernesto: niente indici FTS5, solo una grep in sandbox.
- **Regole di risposta in `context/soul.md`** dalla valutazione di i-have-adhd: apri con la risposta o l'azione, lavori in piu' passi come lista numerata, errori riferiti come fatti con la mossa successiva, chiusura col prossimo passo concreto (non un riepilogo), elenchi lunghi raggruppati per tema. Scartate di proposito: restate dello stato a ogni turno (spreca token), stime in minuti (falsa precisione), cap a 5 voci (le rassegne ne hanno 10).

## [0.16.0] - 2026-09-18

### Aggiunto
- **`telegram_send` e `telegram_read`**: messaggi Telegram tramite Bot API. L'invio va al canale di default (`TELEGRAM_CHAT_ID`) o a una chat passata a chiamata, chiede conferma come azione esterna e spezza i testi oltre i 4096 caratteri sui confini di riga; `parse_mode` opzionale (HTML/MarkdownV2). La lettura usa `getUpdates` senza consumare la coda: restituisce gli aggiornamenti recenti (messaggi diretti e post dei canali dove il bot e' amministratore), non la cronologia, che la Bot API non espone.
- Credenziali `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` documentate in `credentials.md`.

## [0.15.0] - 2026-09-18

### Aggiunto
- **La compattazione automatica chiede conferma in sessione interattiva**: al superamento della soglia viene domandato una volta per turno se riassumere i vecchi risultati strumento (default si'; e' manutenzione, non un'azione pericolosa). In modalita' non presidiata resta automatica.
- **Retry sulle cadute di rete a meta' stream**: "Network connection lost" arriva a risposta iniziata, dove i retry del SDK non operano. La chiamata e' idempotente e il parziale non e' ancora in storia, quindi `run_turn` la ripete identica fino a due volte con attesa crescente (5s, 10s), annunciando il tentativo per non sembrare una ripetizione del testo gia' stampato. Esauriti i tentativi la storia si riavvolge come prima.

### Cambiato
- **Soglia di compattazione da 60k a 90k token stimati**: sotto i 90k la storia resta integra; con i lotti di articoli della rassegna newsletter le soglie basse facevano partire la compattazione a meta' lavoro.
- **Read timeout da 180s a 300s**: un provider lento su un prompt grande puo' stare minuti prima del primo token senza essere morto; se lo stream si arena davvero, il retry di `run_turn` rilancia la chiamata.
- **L'agente si presenta come "Ernesto"** invece che col nome del modello, in ciano in grassetto sul terminale: in chat conta chi parla, il modello si legge nel banner e in `/context`.
- **Niente piu' righe vuote a ripetizione in chat.** Due correzioni di stampa (la storia conserva il contenuto originale): gli a-capo e gli spazi prima del primo carattere visibile non si stampano — nei turni con tool call il modello emetteva solo "\n\n", che sommati al separatore delle righe di step davano due o tre righe vuote tra uno step e l'altro — e a risposta iniziata le righe vuote ripetute collassano a una sola.

## [0.14.0] - 2026-09-18

### Corretto
- **Le chiamate API arenate non tengono piu' la sessione in stallo per dieci minuti.** Il client OpenAI nasceva col timeout di default del SDK (read 600s, due retry): un provider lento su prompt grandi sembrava una sessione morta e la rassegna newsletter si e' interrotta due volte a meta'. Ora il read timeout e' 180s: lo stream fermo fallisce in fretta e il SDK ritenta da solo.
- **La compattazione non portava via gli id appena selezionati.** La soglia passa da 30k a 60k token stimati: con i lotti di articoli della rassegna (JSON da decine di migliaia di caratteri) a 30k la compattazione partiva a meta' lettura e il modello doveva recuperare gli id dal log di sessione.

### Aggiunto
- `newsletter_query` accetta `format="table"`: una riga per articolo (id, data, fonte, titolo) per la panoramica iniziale, che in JSON con estratti arrivava a ~19k token per 149 articoli. Il playbook la usa per la shortlist e legge i contenuti estesi a blocchi di al massimo 10 id.
- Tetto dell'output di `newsletter_query` ridotto a 25.000 caratteri.

## [0.13.0] - 2026-09-18

### Aggiunto
- **`newsletter_query`**: interroga l'archivio degli articoli AI raccolti dal progetto newsletter (cartella parallela, DB SQLite) lanciando il suo `query_articles.py` in subprocess con l'interprete corrente: lo script e' stdlib-only, quindi niente dipendenza dal venv dell'altro progetto. Filtri per finestra in giorni (`days`, default da `newsletter.days` in `config.yaml`, altrimenti 4), fonte, id puntuale, contenuto esteso e conteggio. Con `ids` il filtro temporale si disattiva: e' la fase due, la rilettura integrale della sola shortlist. I contenuti estesi vengono tagliati a 2000 caratteri per articolo: venti articoli interi da diecimila caratteri saturerebbero la storia a ogni step successivo.
- **Marcatura degli articoli elaborati** con `mark_processed=true`: scrive su un DB fuori dalla sandbox, quindi chiede conferma come `LEVEL_WARNING` e in dry-run simula. La scrittura resta nello script del progetto newsletter, che la marcia solo sulle righe gia' restituite dalla stessa selezione.
- **`playbooks/rassegna-newsletter.md`**: la procedura "novita' AI via email": conteggio, panoramica a estratti, lettura integrale della shortlist, dieci articoli scelti per significativita', email HTML essenziale con titolo, fonte, data, riassunto in italiano e link, e marcatura di tutto il lotto valutato solo dopo l'invio riuscito. Il lotto si marca intero, non solo i dieci inviati, altrimenti il backlog non processato crescerebbe a ogni giro.
- Sezione `newsletter` (`dir`, `days`) in `context/config.yaml`.

## [0.12.0] - 2026-09-18

### Cambiato
- **Le conferme non presidiate si risolvono da sole.** Con `--prompt` o `--file` nessuno puo' rispondere: le azioni ordinarie (email, spostamenti, percorsi fuori dalla cartella di lavoro) vengono approvate e annotate nel log, quelle distruttive (denylist dei comandi, eliminazione di posta) negate. Prima la conferma restava appesa su un terminale e veniva rifiutata in cron, dove pero' il compito falliva in silenzio.
- **Un rifiuto distruttivo interrompe l'esecuzione** invece di tornare al modello come errore: `run_turn` esce dal loop e il processo termina con uscita **3**, distinta dal tetto di spesa (2) e dagli errori di avvio (1). Il motivo del rifiuto entra nel log come evento `conferma`.

### Corretto
- **Le conferme non si bloccano piu' fuori da una console Windows.** Il controllo su `sys.stdin.isatty()` non bastava: `questionary` apre il terminale per conto proprio e sotto git bash falliva con `Found xterm-256color, while expecting a Windows console`, trasformando la conferma in un errore dello strumento. In modalita' non presidiata `questionary` non viene piu' invocato.

### Aggiunto
- Regola in `context/identity.md`: non si rifa' con la shell cio' che uno strumento dedicato ha rifiutato o non ha potuto fare. Nelle prove l'agente, visto fallire `send_email`, ha provato per cinque minuti a mandare la stessa email con `curl`, con un file `.cmd` e con uno script Python, cioe' saltando anteprima, conferma e registro.

## [0.11.0] - 2026-09-18

### Aggiunto
- **Posta in arrivo**: cinque strumenti su una casella IMAP — `imap_folders` (cartelle con i conteggi), `imap_list` (messaggi piu' recenti, filtrabili per non letti e per testo in mittente e oggetto), `imap_read` (intestazioni, corpo con l'HTML convertito in testo, allegati elencati e su richiesta salvati), `imap_move` e `imap_delete`. Le credenziali sono `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER` e `IMAP_PASSWORD`, dichiarate in `credentials.md` come le altre. Il protocollo lo parla `imap-tools`, nuova dipendenza senza sotto-dipendenze: i centocinquanta righe di UTF-7 modificato, decodifica degli header e aritmetica degli UID non aggiungevano niente al problema e tre di esse hanno conseguenze distruttive se sbagliate.
- **`playbooks/gestione-posta.md`**: la procedura di triage, il divieto di agire in blocco senza aver mostrato l'elenco, la regola che gli uid si rielencano invece di ricordarli.
- **`send_email` manda anche HTML**: parametro `html` opzionale, con `text` che resta obbligatorio come versione alternativa. L'anteprima di conferma continua a mostrare il testo e segnala quanti caratteri pesa la parte HTML: il sorgente riempirebbe i 500 caratteri dell'anteprima di `<head>` e la conferma diventerebbe cieca. Finora l'agente che voleva mandare una email formattata doveva scriversi uno script che chiamava l'API da se', fuori da ogni conferma.

### Cambiato
- `html_to_text()` esce da `FetchUrlTool` e diventa una funzione di `tools/web.py`, condivisa con la lettura delle email: ridurre una pagina web e ridurre una newsletter sono lo stesso problema. Una newsletter da 60 KB vale 15.000 token grezzi e 1.250 convertita, e la compattazione automatica arriverebbe troppo tardi per evitarli.
- `context/identity.md` dichiara che il testo proveniente da fuori (email, pagine, file altrui) e' materiale da leggere e non un ordine da eseguire.

## [0.10.0] - 2026-09-18

### Aggiunto
- **Tetto di spesa della sessione**, predefinito a 2 dollari e regolabile con `--max-cost` (`0` lo toglie). Il controllo e' a turno finito, perche' il costo di una chiamata si conosce solo con la risposta: il tetto puo' essere superato dell'ultimo turno, mai di piu'. In sessione interattiva ernesto chiede se proseguire per un altro scatto dello stesso importo, e il nuovo tetto riparte dalla spesa corrente, cosi' ogni conferma concede lo stesso margine anche quando l'ultimo turno ha sforato; rispondendo di no la sessione si chiude. Con `--prompt` o `--file`, dove nessuno puo' rispondere, l'esecuzione termina con uscita **2**, distinguibile da un errore qualsiasi. Ogni esito entra nel log JSONL come evento `budget`, con spesa, tetto e decisione.
- La conferma di spesa non passa da `--yolo`: quel flag disattiva le conferme sulle azioni pericolose, non il tetto, che difende il portafoglio e non i file.

### Cambiato
- **`--prompt-file` si chiama `--file`.** Nome piu' corto per un'opzione che si usa spesso a mano.
- **Il file viene verificato prima di ogni altra cosa**: se il percorso non esiste, o non e' un file, l'avvio si ferma con `Errore: file non trovato: ...` e uscita 1, senza caricare contesto ne' prezzi. Prima l'errore arrivava dal sistema operativo, con testo diverso a seconda del caso (una cartella dava `PermissionError` su Windows).

## [0.9.0] - 2026-09-18

### Aggiunto
- **Il tetto di step diventa regolabile**, da riga di comando con `--max-steps N` e a sessione aperta con `/step N` (senza argomento mostra il valore in vigore e quello predefinito). Il guard rail resta a 30 step se non si dice altro: serve a fermare un modello che chiama strumenti a vuoto, ma un compito lungo puo' averne bisogno di piu' e uno rischioso di meno. Il valore attivo compare anche in `/context`.

### Cambiato
- `MAX_AGENT_STEPS` non e' piu' letta direttamente dal loop: resta il valore predefinito, mentre il limite in vigore vive in `SessionState.max_steps`. Le righe di step e il messaggio del guard rail mostrano il limite della sessione.

## [0.8.0] - 2026-09-18

### Aggiunto
- **`--json`**: attiva il formato JSON delle risposte dalla riga di comando, disattivo per impostazione predefinita. Ha la precedenza su `model.json_mode` di `config.yaml`, e un modello che non dichiara `response_format` non lo riceve, con un avviso all'avvio. Come gia' avveniva con `/model`, il JSON mode tiene disattivati gli strumenti: `response_format` e tool calling insieme fanno descrivere la chiamata invece di eseguirla.
- **`--prompt-file PATH`**: prende da un file il messaggio del turno non presidiato, per i prompt lunghi o gia' scritti altrove. Insieme a `--prompt` i due si uniscono in un solo messaggio, prima il file (contesto) e poi l'istruzione. Un file illeggibile ferma l'avvio prima di caricare contesto e prezzi, con errore ed exit code 1.
- **Tempi accanto a token e costo**: ogni risposta riporta la durata del turno e il tempo speso dall'inizio della sessione, per esempio `[4.1k tok in / 317 tok out · $0.0017 · 16,5s · 21,5s tot]`; il cumulativo compare anche in `/log` e nell'istantanea di `/save`. Il turno e' misurato per intero, strumenti e attese di conferma compresi, ed e' registrato anche quando finisce in errore o interrotto con Ctrl+C, cosi' il totale non perde pezzi.

## [0.7.1] - 2026-09-17

### Cambiato
- **`context/credentials.md` entra nel bundle**: dichiara quali variabili d'ambiente servono, a cosa, dove ottenerle e con quali limiti, ma non ne contiene i valori, che vivono nell'ambiente o in `.env`. Sul computer di destinazione e' proprio il file che spiega come configurare le chiavi, quindi tenerlo fuori toglieva istruzioni senza proteggere nulla. Fuori dal bundle resta il solo `.env`.

## [0.7.0] - 2026-09-17

### Aggiunto
- **`build_bundle.py`: un bundle che parte dove Python non c'e'**. Costruisce in `dist/` una cartella autonoma con il runtime embeddable di Python 3.12 scaricato da python.org, le dipendenze di `requirements.txt` installate al suo interno e i sorgenti del progetto, piu' lo zip pronto da copiare (circa 70 MB di cartella, 28 di archivio). Si avvia con il proprio `ernesto.cmd` senza interprete di sistema, senza connessione e senza installare niente sul computer ospite: il file `._pth` del runtime viene riscritto perche' `sys.path` comprenda il bundle e le sue librerie, e nient'altro. Serve quando il computer di destinazione non ha Python e non lo si puo' installare; negli altri casi resta piu' comodo copiare il progetto senza `.venv` e lasciare che il launcher lo ricostruisca.
- `.env` e `context/credentials.md` sono esclusi dal bundle per costruzione, con un test che lo verifica: l'archivio nasce per essere spostato, le chiavi API restano sul computer che lo costruisce.

## [0.6.3] - 2026-09-17

### Cambiato
- **I launcher ricostruiscono il virtualenv quando non e' utilizzabile**: `ernesto.cmd` e `ernesto.sh` non si limitano piu' a controllare che `.venv/Scripts/python.exe` esista, lo eseguono. Un virtualenv contiene le dipendenze ma non l'interprete: il suo python e' un guscio che cerca la libreria standard nel percorso assoluto scritto in `pyvenv.cfg`, percorso che su un altro computer non esiste, e li' il file c'e' ma non parte. Se la prova fallisce il launcher cancella il virtualenv inservibile, ne crea uno nuovo con il Python dell'ospite (`py -3`, poi `python`, ciascuno provato davvero perche' su Windows `python` puo' essere il segnaposto del Microsoft Store), installa `requirements.txt` e prosegue con l'avvio. Cosi' la cartella del progetto si sposta da un computer all'altro senza portarsi dietro `.venv`.
- **`.gitattributes`** fissa i fine riga dei launcher a prescindere dal computer su cui si fa il clone: `eol=lf` per `.sh`, che con i ritorni a capo di Windows verrebbe rifiutato dall'interprete, `eol=crlf` per `.cmd`.

## [0.6.2] - 2026-09-17

### Rimosso
- **Cartella `docs/`**: il benchmark a cinque esercizi (fixture, prompt, verifiche e scorecard), il materiale storico di `docs/contesto-originale/` e i due prompt `kimi-code-chat-agent` escono dal repository. Erano documenti di una fase di progettazione ormai conclusa, fermi a un'architettura che il codice ha nel frattempo superato, e la loro presenza suggeriva una procedura di verifica che nessuno esegue piu'.

### Cambiato
- `CLAUDE.md` e `.gitignore` non citano piu' `docs/`, che non esiste piu'.
- `rassegne/` entra in `.gitignore` accanto a `memories/` e `workspace/`: e' output prodotto dall'agente durante le sessioni, non contenuto del progetto.

## [0.6.1] - 2026-09-17

### Cambiato
- **I launcher passano nella radice del repository**: `ernesto.cmd` e `ernesto.sh` al posto di `bin/ernesto.cmd` e `bin/ernesto`. Cosi' basta mettere la radice nel PATH invece di una sottocartella. Lo script per shell prende l'estensione `.sh` perche' un file `ernesto` non puo' convivere con il package `ernesto/` nella stessa cartella.

## [0.6.0] - 2026-09-17

### Aggiunto
- **Skill caricabili su richiesta**: una skill e' un corpo di conoscenza specialistica in `skills/<nome>/SKILL.md`, con frontmatter `name` e `description`. Si attiva con `/skill` (menu con le frecce, o elenco numerato dove il terminale non lo consente) e resta nel system prompt per la sessione; `/skill off` la rimuove. Nel prompt entrano sempre solo nome e descrizione di quelle disponibili, cosi' il modello puo' proporne l'attivazione senza che i corpi pesino in ogni richiesta. Le skill si cercano nella cartella di lavoro e in `~/.config/ernesto/skills/`: a parita' di nome vince quella del progetto.
- **Skill `wordpress`** come esempio e primo caso d'uso: trinita' della sicurezza, hook, query, struttura di un plugin, errori ricorrenti.
- `_select()` in `cli.py`: menu a frecce con fallback numerico automatico quando questionary non riesce a inizializzarsi.

### Cambiato
- **Menu del completamento leggibile**: testo bianco su sfondo nero, voce selezionata a colori invertiti, descrizioni in grigio.
- **Il modello dei riassunti passa a `qwen/qwen3.8-27b`** (era Gemini 2.5 Flash), sempre configurabile con `compact.summary_model`.
- `refresh_system_prompt(force=True)` ricompone il prompt anche quando le memorie non sono cambiate: serve dopo `/skill`, che cambia il contesto senza toccarle.
- `identity.md` distingue esplicitamente playbook (procedure che il modello consulta da se') e skill (conoscenza che l'utente attiva), perche' due meccanismi vicini senza confine dichiarato finiscono per confondersi.

## [0.5.0] - 2026-09-17

### Aggiunto
- **Completamento dei comandi**: digitando `/` compaiono tutti i comandi con la loro descrizione, si filtrano scrivendo e si scelgono con le frecce. Il prompt passa a `prompt_toolkit`, che porta anche storia e modifica della riga; se il terminale non lo supporta (git bash solleva `NoConsoleScreenBufferError`) si ricade su `input()` senza errori.
- **Comando `/command`**: elenco dei comandi con una descrizione breve.
- **`/context files`**: i percorsi completi di tutti i file letti all'avvio, memorie e log compresi, distinguendo «non trovato» da «identico al globale».
- **Launcher `bin/ernesto.cmd` e `bin/ernesto`**: lanciano ernesto con il Python del `.venv` da qualunque cartella, senza percorsi assoluti cablati. La cartella di lavoro resta quella corrente, che e' la workdir dell'agente.

### Cambiato
- **Una sola regola di caricamento per tutti i file di contesto**: `soul.md`, `identity.md` e `credentials.md` sommano il file globale di `~/.config/ernesto/context/` e quello del progetto, nell'ordine. Prima solo `identity.md` si sommava e gli altri due venivano presi dal primo posto in cui comparivano, quindi un `soul.md` globale poteva essere ignorato senza che nulla lo dicesse. Per `soul.md` il frontmatter `mode: replace` vale se sta in una qualsiasi delle due posizioni; due file con contenuto identico vengono caricati una volta sola.
- **`/context` compatto**: un blocco solo con modello, percorsi di base, tabella dei token per file con la provenienza, storia, strumenti e stato. Prima erano venti righe con il totale ripetuto tre volte e un percorso completo per riga.
- **Il banner non elenca piu' i comandi**: al loro posto un rimando a `/command`. L'elenco veniva comunque troncato dal box.
- I comandi sono definiti una volta sola in `COMMANDS` (`cli.py`), da cui nascono completamento, `/command` e aiuto; un test verifica che coincidano con i rami di `handle_command`.

## [0.4.0] - 2026-09-17

### Aggiunto
- **Contesto installabile a livello utente**: i file versionati in `context/` si copiano in `~/.config/ernesto/context/` con `install-context.py`, e da li' valgono in qualunque cartella di lavoro. Contengono identita', profilo utente, disciplina di codice, regole di memoria e di sicurezza, ricavate dai file di contesto usati in altri progetti (materiale di origine e criteri di scelta in `docs/contesto-originale/`).
- **Cartella `workspace/`**: lo spazio dell'agente per appunti, bozze e output intermedi, con `workspace/projects/<nome>/` come casa dei progetti nuovi. `identity.md` lo dichiara, cosi' "voglio creare un progetto pippo" finisce nel posto giusto.
- **Opzione `--prompt`**: esegue un solo turno e termina, senza REPL ne' banner, per cron e script. In questa modalita' l'avvio non pone domande interattive, altrimenti un'esecuzione non presidiata resterebbe appesa su una richiesta che nessuno vede.
- **Playbook per le attivita' ricorrenti**: file in `playbooks/`, elencati in `identity.md` e letti con `read_file` solo quando servono, quindi a costo zero finche' non si usano. Il primo e' `playbooks/rassegna-stampa.md`.
- **`install-context.py`**: installa il contesto di base e ricrea `workspace/projects/` e `memories/` dopo un clone.

### Cambiato
- **Tutti i file letti all'avvio stanno in `context/`**, con la stessa struttura nella cartella di lavoro e in `~/.config/ernesto/`: `soul.md`, `identity.md`, `credentials.md`, `config.yaml` e `mcp.json`. Nella radice resta solo `.env`. Prima erano sparsi fra radice e cartella di configurazione, con una regola diversa per ciascuno.
- **`agent.md` si chiama `identity.md`** e **si somma invece di sostituire**: prima quello di `~/.config/ernesto/context/`, poi quello del progetto, etichettati separatamente in `/context`. Prima un `agent.md` dentro un progetto faceva sparire tutte le regole generali.
- **La sezione `solo-progetto` di `identity.md`** e' esclusa dalla copia globale e, quando la cartella di lavoro e' questo repository, viene caricata da sola: senza, le regole generali sarebbero entrate due volte nel prompt (1,5k token di duplicazione misurati).
- **Le memorie stanno tutte in `memories/`**: la persistente e' `memories/memory.md`, accanto a quelle di sessione. `memories/` e `workspace/` sono escluse da git: sono dati dell'agente, non del progetto.
- **`/context` mostra il percorso completo di ogni file letto**, compresi quelli non trovati e le memorie, oltre alla stima token di ciascuna parte del system prompt.
- **`.env` viene cercato anche in `~/.config/ernesto/`** come fallback dopo quello della cartella di lavoro: senza, lanciare ernesto su un progetto qualsiasi avrebbe richiesto di copiare le chiavi in ogni cartella.
- Radice ripulita: prompt del benchmark e documenti storici in `docs/`, esempi di configurazione in `context/`.

## [0.3.0] - 2026-09-17

### Aggiunto
- **Memoria a due livelli**: `memory.md` persistente per il progetto e `memories/memory-<timestamp>.md` per la singola sessione (stesso timestamp del log). Entrambe scritte e potate dall'agente con gli strumenti esistenti, senza nuovi strumenti da pagare in token a ogni step.
- **Comando `/load`**: riprende una sessione salvata ripristinando la storia con le `tool_calls` intatte. `/save` ora scrive anche un `.json` accanto al `.txt`, perche' il testo perdeva `tool_calls` e `tool_call_id` e non era ricaricabile. Il salvataggio viene validato prima di sostituire la storia: un file manomesso produce un errore leggibile invece di una richiesta che l'API rifiuta.
- **Riassunto della compattazione generato da un modello**: `/compact llm` lo usa su richiesta; nella compattazione automatica viene proposto con conferma solo se `compact.llm_summary` e' attivo in `config.yaml`. Se il modello non risponde si ricade sul riassunto deterministico: un percorso che serve a risparmiare non deve poter far fallire il turno.
- **`config.yaml` come configurazione utente**: modello iniziale (`model.default`), JSON mode all'avvio, modello dei riassunti (`compact.summary_model`) e denylist aggiuntiva. Cercato nella cartella di lavoro e poi in `~/.config/ernesto/`; vedi `config.yaml.example`. `pyyaml` diventa una dipendenza dichiarata.
- **Conferme differenziate per gravita'** (C10): etichette ASCII e colori distinti per azioni distruttive (rosso), verso l'esterno (giallo) e fuori dalla cartella di lavoro (ciano). Il colore si applica solo quando l'output e' un terminale.

### Cambiato
- **Le memorie non entrano piu' nel system prompt**: entra solo il loro indice (nome, dimensione, prima riga) e il modello legge il contenuto con `read_file` quando gli serve. Prima `memory.md` viaggiava integralmente in ogni richiesta di ogni step anche quando non c'entrava nulla con il task.
- **Modello di default**: Qwen 3.8 27B al posto di Gemma free, con JSON mode disattivato, sovrascrivibile da `config.yaml` e da `--model`.
- **Denylist meno aggirabile** (C7): il comando viene normalizzato (minuscole, spazi collassati) e i pattern coprono `rm -r -f`, `rm --recursive --force`, `RM -RF` e `git -C . push`. Resta una difesa contro la disattenzione, e ora il codice e il README lo dicono.

## [0.2.0] - 2026-09-17

### Aggiunto
- **Strumento `fetch_url`**: scarica una pagina web e restituisce il testo leggibile, senza HTML, script e menu (parser basato su `html.parser` della stdlib, nessuna nuova dipendenza). Prima, per leggere un risultato di ricerca, il modello poteva solo usare `curl` da `run_command` e riceveva HTML grezzo troncato a meta'.
- **`RESEND_FROM_NAME`**: nome visualizzato del mittente usato come default da `send_email` quando il modello non passa `from_name` (prima il default era la costante `Chat CLI` e la variabile veniva ignorata). Documentata in `credentials.md` insieme ai vincoli sul dominio verificato.
- **Compattazione della storia**: oltre i 30.000 token stimati i risultati degli strumenti piu' vecchi di tre giri diventano un riassunto deterministico (nome dello strumento, argomenti, dimensione, testa e coda), con il contenuto integrale che resta nel log JSONL. La compattazione riscrive solo il campo `content` dei messaggi `tool`: non rimuove nulla, quindi le coppie assistant/tool e il rewind su errore restano intatti. Comando `/compact [giri]` per farla subito; `/context` e `/log` mostrano soglia e token risparmiati.
- **Memoria di lavoro `memory.md`**: quarto file di contesto, cercato solo nella cartella di lavoro, che l'agente scrive e pota da se' con `edit_file`. Rientra nel system prompt a ogni turno (non a ogni step, per non rompere il prompt caching), sopravvive a `/clear` e alle sessioni successive, ed e' troncato a 4000 caratteri.
- **Guardia sui percorsi in `run_command`**: percorsi assoluti e risalite con `..` fanno scattare una richiesta di conferma. La sandbox non ha mai coperto `run_command`, che esegue una shell arbitraria: README e `CLAUDE.md` ora lo dicono invece di promettere un confine che non c'era.

### Corretto
- **`run_command` non perde piu' l'output non decodificabile**: la `Popen` usava `text=True` senza `encoding`, quindi la decodifica avveniva nella codifica locale (`cp1252` su Windows) dentro il thread lettore di `communicate()`; l'eccezione non risaliva al chiamante e lo strumento restituiva `exit 0` con output vuoto. In una sessione reale il modello ha interpretato il vuoto come "pagina protetta da JS" e ha bruciato quattro step e ~18k token. Ora `encoding="utf-8", errors="replace"`.
- **`brave_search` ritenta una volta sul `429`** dopo 1,1 secondi (il piano gratuito consente 1 richiesta al secondo, e nel loop agentico due ricerche consecutive partono a pochi millisecondi di distanza); se il limite persiste l'errore lo nomina invece di essere generico. Gli snippet vengono ripuliti dal markup HTML, che finora entrava nel contesto a ogni ricerca.

### Cambiato
- **`run_command` separa stdout e stderr** (prima `stderr=STDOUT` li fondeva): con entrambi presenti l'output e' etichettato, con tetti di troncamento indipendenti (8000 caratteri per stdout, 2000 per stderr), cosi' il rumore di npm o pip non mangia il segnale.
- **`run_command` non eredita piu' lo stdin del terminale** (`stdin=DEVNULL`): un comando interattivo fallisce subito con un errore leggibile invece di restare appeso fino al timeout di 120 secondi consumando l'input dell'utente.
- **L'errore di sandbox dice come rimediare**: include la cartella di lavoro e ricorda che i percorsi vanno espressi relativi a essa. I messaggi d'errore sono l'unico canale con cui gli strumenti insegnano al modello a usarli.

## [0.1.3] - 2026-09-16

### Aggiunto
- **Gestione delle interruzioni con Ctrl+C**: durante lo streaming annulla il turno e ripristina la storia; durante `run_command` uccide l'intero albero del processo (`taskkill /F /T` su Windows, `killpg` altrove) prima di annullare — prima il processo figlio restava orfano e il terminale sembrava bloccato. Al prompt, Ctrl+C esce.
- **UI di avvio**: schermo pulito e banner incorniciato (versione, modello, reasoning, workdir, contesto, log, comandi); avvisi di avvio stampati sotto il banner; riga di separazione sopra la zona di input a ogni prompt.

### Cambiato
- `run_command` usa `subprocess.Popen` con gruppo di processi separato (al posto di `subprocess.run`) per consentire la terminazione controllata su timeout e Ctrl+C.

## [0.1.2] - 2026-09-16

### Corretto
- **`list_files` ricorsivo non elenca più le cartelle generate** (`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `dist`, `build`): prima una ricorsione sulla root poteva iniettare ~8k token di rumore nel contesto, rispediti all'API a ogni step del loop (misurato in una sessione reale: prompt passato da ~2k a ~17k token per step, costo sessione quasi triplicato). La descrizione dello strumento dichiara l'esclusione al modello.

## [0.1.1] - 2026-09-16

### Corretto
- **JSON mode e tool calling non sono più inviati insieme**: con `response_format: json_object` attivo, alcuni provider (es. Qwen 3.8) rispondevano con un blob JSON testuale che *descriveva* una tool call invece di eseguirla, quindi gli strumenti non partivano mai. Ora in JSON mode gli strumenti sono disattivati, con avviso esplicito all'attivazione in `/model` e indicazione in `/context` ("Strumenti: DISATTIVATI (JSON mode attivo)").
- Aggiunti test di regressione: con JSON mode i `tools` non vengono passati all'API; senza JSON mode sì (45 test totali).

## [0.1.0] - 2026-09-16

### Aggiunto
- Agente da terminale **ernesto** con loop agentico: streaming con tool calls, esecuzione strumenti e rilancio fino a risposta finale, guard rail `MAX_AGENT_STEPS=30`.
- Strumenti nativi:
  - `list_files`, `read_file`, `write_file`, `edit_file` con sandbox obbligatoria sulla cartella di lavoro;
  - `run_command` con timeout, troncamento output a 8000 caratteri e denylist di pattern pericolosi;
  - `brave_search` (API Brave Search, richiede `BRAVE_API_KEY`);
  - `send_email` (API Resend, richiede `RESEND_API_KEY` e `RESEND_FROM`).
- Integrazione MCP opzionale: server stdio configurabili via `mcp.json`, strumenti registrati come `mcp__<server>__<tool>`.
- File di contesto letti all'avvio dalla cartella di lavoro (fallback `~/.config/ernesto/`):
  - `soul.md` (personalità, frontmatter `mode: replace|append`);
  - `agent.md` (istruzioni operative del progetto);
  - `credentials.md` (dichiarazione delle variabili d'ambiente richieste, con verifica all'avvio e masking dei valori nei log).
- Log di sessione JSONL in `logs/session-*.jsonl` con contabilità dei costi cumulativa e mascheramento dei segreti.
- Costi e token sempre visibili: prompt indicator `Tu [in · out · $]>`, riga di riepilogo dopo ogni step del loop agentico.
- Interfaccia di avvio con `typer`: `--workdir`, `--model`, `--yolo`, `--dry-run`, `--reasoning`, `--no-mcp`; conferme e menu con `questionary`.
- Nuovi comandi interattivi: `/context`, `/clear`, `/yolo`, `/tools`, `/log`, `/cost`, `/reasoning`.
- Modalità `--dry-run` per simulare write/edit/email/comandi senza effetti collaterali.
- Suite di test `pytest` (sandbox, troncamento, denylist, parsing JSON malformato, tool senza API key, file di contesto, masking log) e lint con `ruff`.

### Mantenuto dal precedente `chat.py` (v0.2.2)
- Registry dei modelli con selezione via `/model`, prezzi caricati a runtime da `GET /api/v1/models`.
- Streaming delle risposte con `stream_options={"include_usage": True}` e stampa del costo dopo ogni risposta.
- Comandi `/model` (con reset conversazione e richiesta JSON mode), `/save`, `exit`/`quit`, Ctrl+C.
- Gestione errori API con ripristino dello stato della conversazione.
- Aggiunto al registry il modello `qwen/qwen3.8-27b` ("Qwen 3.8 27B").

### Cambiato
- `chat.py` è sostituito da `ernesto.py` (entry point) + pacchetto `ernesto/`.
- `.env` non richiede più `python-dotenv`: parser interno minimale usato come fallback per popolare le variabili d'ambiente; la fonte dichiarativa delle credenziali è `credentials.md`.
