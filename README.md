# ernesto

**ernesto** è un agente da terminale in Python che parla con i modelli LLM tramite
[OpenRouter](https://openrouter.ai) e può agire sulla macchina: leggere e scrivere
file, eseguire comandi, cercare sul web, inviare email e integrare strumenti MCP.

Nasce come evoluzione di una semplice CLI di chat (`chat.py`): ne conserva tutte
le funzionalità (registry modelli, streaming, costi per risposta, `/model`, `/save`)
e aggiunge un loop agentico completo con strumenti e policy di sicurezza.

## Requisiti

- Python 3.10+
- Una chiave API OpenRouter (`OPENROUTER_API_KEY`)
- Opzionali: `BRAVE_API_KEY` (ricerca web), `RESEND_API_KEY` + `RESEND_FROM` (invio email),
  `IMAP_HOST` + `IMAP_USER` + `IMAP_PASSWORD` (posta in arrivo)

## Installazione

```bash
git clone https://github.com/mavidasnc/ernesto.git
cd ernesto
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Per sviluppo (test + lint):

```bash
pip install -r requirements-dev.txt
```

## Avvio

```bash
python ernesto.py                 # oppure: python -m ernesto
```

Per lanciarlo da qualunque cartella ci sono `ernesto.cmd` (e `ernesto.sh` per git bash e
WSL) nella radice del repository: usano il Python del `.venv` e mantengono come cartella di
lavoro quella da cui li lanci. Aggiungi la radice del repository al PATH, oppure copia il
`.cmd` in una cartella già nel PATH facendolo puntare a quello del repository.

### Spostare ernesto su un altro computer

Copia la cartella del progetto **senza `.venv`** e lancia `ernesto.cmd`: se il virtualenv
manca, o se è stato copiato da un'altra macchina e quindi non parte, il launcher lo
ricostruisce con il Python del computer ospite e installa `requirements.txt`, poi avvia
l'agente. Servono un Python 3.12 o successivo nel PATH e una connessione a internet al
primo avvio; dalle volte successive parte diretto.

Copiare il `.venv` non evita quel passaggio, anzi: un virtualenv non contiene
l'interprete, solo le dipendenze e un guscio che cerca la libreria standard nel percorso
assoluto registrato in `pyvenv.cfg` al momento della creazione. Su un altro computer quel
percorso non esiste, il guscio si ferma con `No Python at '...'`, e il launcher fa comunque
da capo scartando la copia inservibile. Sono 110 MB che nello zip si risparmiano.

### Un bundle che parte senza Python installato

Quando sul computer di destinazione Python non c'è e non si può installare, si costruisce
un bundle autonomo, che include il runtime:

```bash
python build_bundle.py            # dist/ernesto/ e dist/ernesto-<versione>-win64.zip
python build_bundle.py --no-zip   # solo la cartella
```

Lo script scarica da python.org il pacchetto *embeddable* di Python 3.12 (una decina di
MB), installa dentro il bundle le dipendenze di `requirements.txt` e copia i sorgenti; il
risultato sono circa 70 MB di cartella, 28 di zip. Si copia dove si vuole, anche su una
chiavetta, e si avvia con il suo `ernesto.cmd`: non serve Python, non serve una
connessione, non si tocca nulla del computer ospite.

Il bundle si costruisce su Windows a 64 bit, perché i pacchetti compilati vengono scelti
per l'interprete che li installa, e va ricostruito quando cambiano le dipendenze o i
sorgenti. L'unico file che resta fuori è `.env`: le chiavi API vanno messe sul computer di
destinazione, non spedite dentro l'archivio. `context/credentials.md` invece viaggia con il
bundle, perché dichiara quali variabili servono e dove ottenerle senza contenerne i valori.

Con `--json` le risposte arrivano come oggetto JSON e gli strumenti restano disattivati per
tutta la sessione, perché `response_format` e il tool calling non convivono: il modello
descriverebbe la chiamata in un blob di testo invece di eseguirla. I modelli che non
dichiarano il supporto lo ignorano, e l'avvio lo segnala.

`--file` serve quando il turno è lungo o vive già in un file: il contenuto diventa il
messaggio dell'utente. Usato insieme a `--prompt`, il file fa da contesto e il messaggio da
istruzione, in quest'ordine:

```bash
python ernesto.py --file rapporto.md --prompt "riassumi in cinque punti"
```

Se il percorso non esiste, o non è un file, ernesto si ferma prima di caricare qualunque
cosa e lo dice: `Errore: file non trovato: ...`, con uscita 1.

### Tetto di spesa

Ogni sessione ha un tetto predefinito di **2 dollari**, che si cambia con `--max-cost` e si
toglie del tutto con `--max-cost 0`. Il controllo avviene a turno finito, perché il costo di
una chiamata si conosce solo quando la risposta è arrivata: il tetto può quindi essere
superato dell'ultimo turno, mai di più.

Al superamento il comportamento dipende da chi sta guardando. In sessione interattiva
ernesto chiede se proseguire per un altro scatto dello stesso importo, e il nuovo tetto
riparte dalla spesa corrente, così ogni conferma concede sempre lo stesso margine; se
rispondi di no, la sessione si chiude. Con `--prompt` o `--file`, dove nessuno può
rispondere, l'esecuzione termina subito con **uscita 2**, distinguibile da un errore
qualunque per chi incatena più esecuzioni. In entrambi i casi l'evento finisce nel log
JSONL della sessione, con spesa raggiunta, tetto e decisione presa.

La conferma di spesa non è tra quelle che `--yolo` disattiva: quel flag toglie le conferme
sulle azioni pericolose, non il tetto, che protegge il portafoglio e non i file.

A ogni risposta, accanto a token e costo, compaiono il tempo del turno e quello speso finora
nella sessione: `[4.1k tok in / 317 tok out · $0.0017 · 16,5s · 21,5s tot]`. Il turno è
cronometrato per intero, attese degli strumenti e conferme comprese, perché è il tempo che
aspetti davvero; il cumulativo si ritrova anche in `/log`.

Opzioni (`python ernesto.py --help` per l'elenco completo):

| Opzione | Effetto |
|---|---|
| `--workdir PATH` | Cartella di lavoro (sandbox filesystem e cwd dei comandi) |
| `--model ID` | Modello iniziale (es. `moonshotai/kimi-k2.6`) |
| `--yolo` | Salta tutte le conferme di sicurezza (usare con cautela) |
| `--dry-run` | Simula write/edit/email/comandi senza toccare nulla |
| `--reasoning low\|medium\|high\|xhigh` | Livello di reasoning (default `medium`) |
| `--no-mcp` | Disabilita l'integrazione MCP |
| `--json` | Risposte in formato JSON (`response_format`), disattivo per impostazione predefinita |
| `--max-steps N` | Step massimi del loop agentico per turno (default 30) |
| `--max-cost N` | Tetto di spesa della sessione in dollari (default 2.0; `0` toglie il limite) |
| `--prompt "testo"` | Esegue un solo turno e termina, senza REPL (per cron e script) |
| `--file PATH` | Legge il turno da un file; insieme a `--prompt` il file viene prima |

## Configurazione: i file di contesto

**Tutti i file letti all'avvio stanno in una sottocartella `context/`**, cercata prima nella
cartella di lavoro e poi in `~/.config/ernesto/`. La struttura è identica nei due posti:

```
<cartella di lavoro>/context/     oppure     ~/.config/ernesto/context/
    soul.md
    identity.md
    credentials.md
    config.yaml
    mcp.json
```

L'unica eccezione è `.env`, che resta nella radice della cartella di lavoro (e, come
fallback globale, in `~/.config/ernesto/.env`). Fuori da `context/` stanno anche le cartelle
che l'agente riempie da sé, perché sono dati e non configurazione:

- `memories/` — `memory.md` (persistente) e `memory-<timestamp>.md` (di sessione);
- `workspace/` — appunti, bozze e output intermedi, con `workspace/projects/<nome>/` per i
  progetti nuovi;

entrambe escluse da git e ricreate da `install-context.py`.

`/context` mostra il percorso completo di ogni file effettivamente letto, compresi quelli
non trovati.

Le istruzioni di base (identità, profilo utente, disciplina di codice) stanno in `context/`
di questo repository e si installano una volta sola con:

```bash
python install-context.py
```

Lo script le copia in `~/.config/ernesto/context/`, da dove valgono in **qualunque**
cartella di lavoro, e crea `workspace/projects/` e `memories/`. In `~/.config/ernesto/.env`
conviene tenere le chiavi, lette come fallback quando il progetto non ne ha uno.

`context/identity.md` contiene anche una sezione delimitata dai marcatori `solo-progetto`,
riservata a questo repository: viene esclusa dalla copia globale, e quando si lavora qui
dentro ernesto carica dal file locale solo quel blocco, così le regole generali non entrano
due volte nel prompt.

- **`soul.md`** — personalità e tono dell'assistente. Preposto al system prompt;
  con una riga frontmatter `mode: replace` lo sostituisce del tutto.
- **`identity.md`** — istruzioni operative. È l'unico file che **si somma**: prima quello
  di `~/.config/ernesto/context/` (regole di base valide ovunque), poi quello del progetto
  (convenzioni, comandi di test e lint, vincoli specifici). Un `identity.md` nel progetto
  non cancella le regole generali.
- **`credentials.md`** — dichiara quali variabili d'ambiente servono, a cosa
  servono e come ottenerle. **Non contiene valori reali**: le chiavi stanno
  nelle variabili d'ambiente (o in un `.env` locale, caricato come fallback e
  mai committato). All'avvio ernesto verifica che le variabili dichiarate
  esistano: `OPENROUTER_API_KEY` mancante è un errore fatale, le altre
  producono un avviso e il tool corrispondente risponde con un errore leggibile.
Accanto ai file di istruzioni ci sono le **memorie**, che l'agente scrive e pota da sé:

- **`memory.md`** — memoria persistente del progetto: fatti durevoli, preferenze,
  decisioni. Sopravvive a `/clear` e alle sessioni successive.
- **`memories/memory-<timestamp>.md`** — memoria della singola sessione: stato del lavoro
  in corso ed esiti intermedi. Ha lo stesso timestamp del log, così le due si ritrovano.

Le memorie **non vengono caricate nel contesto**: nel system prompt entra solo il loro
indice (nome, dimensione, prima riga) e il modello ne legge il contenuto con `read_file`
quando ritiene che gli serva. Sono cercate solo nella cartella di lavoro.

I file sono parte del contesto inviato al modello e sono normalmente
leggibili e scrivibili dagli strumenti `read_file`/`write_file`.

## Strumenti disponibili

| Strumento | Cosa fa |
|---|---|
| `list_files` | Elenca file e cartelle (opzionalmente ricorsivo) |
| `read_file` | Legge un file di testo (con offset/limit) |
| `write_file` | Crea o sovrascrive un file (crea le directory intermedie) |
| `edit_file` | Sostituzione esatta chirurgica (`old_string` → `new_string`) |
| `run_command` | Esegue un comando di shell nella cartella di lavoro |
| `brave_search` | Ricerca web via Brave Search API |
| `fetch_url` | Scarica una pagina e ne restituisce il testo leggibile |
| `send_email` | Invio email via Resend, in testo e opzionalmente in HTML |
| `imap_folders` | Cartelle della casella IMAP con messaggi totali e non letti |
| `imap_list` | Messaggi di una cartella, dal più recente, filtrabili |
| `imap_read` | Legge un messaggio: intestazioni, corpo in testo, allegati |
| `imap_move` | Sposta un messaggio in un'altra cartella |
| `imap_delete` | Sposta un messaggio nel cestino (sotto conferma) |
| `mcp__<server>__<tool>` | Strumenti da server MCP configurati in `mcp.json` (opzionale) |

### MCP (opzionale)

Copia `context/mcp.json.example` in `context/mcp.json` e configura i tuoi server stdio; richiede
`pip install mcp`. Se la libreria o un server non sono disponibili, ernesto
parte comunque con un avviso.

## Comandi interattivi

| Comando | Effetto |
|---|---|
| `/model` | Cambia il modello attivo (azzera la conversazione) |
| `/context` | Riepilogo compatto della sessione (`/context files` per i percorsi completi) |
| `/command` | Elenco dei comandi con una descrizione breve |
| `/skill` | Attiva una skill per la sessione (`/skill off` la disattiva) |
| `/clear` | Azzera la conversazione (mantiene log e conteggi cumulativi) |
| `/compact` | Riassume subito i risultati strumento in storia (`/compact N` preserva N giri, `/compact llm` fa riassumere a un modello) |
| `/yolo` | Attiva/disattiva il bypass delle conferme |
| `/tools` | Elenca gli strumenti registrati (nativi + MCP) |
| `/log` | Percorso del log di sessione e riepilogo |
| `/cost` | Costo cumulativo della sessione |
| `/reasoning [livello]` | Mostra o cambia il livello di reasoning |
| `/save` | Salva la sessione in `saves/` (`.txt` da leggere e `.json` da ricaricare) |
| `/load` | Riprende una sessione salvata (`/load` apre l'elenco, `/load <nome>` va diretto) |
| `exit` / `quit` / Ctrl+C | Termina |

Il prompt mostra sempre i cumulativi di sessione: `Tu [24.1k in · 6.3k out · $0.0082]>`.
Digitando `/` compaiono i comandi con la descrizione: si filtrano scrivendo e si scelgono
con le frecce.

> **Nota — JSON mode e strumenti sono incompatibili.** Se attivi il JSON mode
> (alla selezione del modello con `/model`), gli strumenti vengono disattivati:
> `response_format: json_object` impedisce ai provider di emettere tool call
> native. Per usare gli strumenti lascia il JSON mode disattivato; `/context`
> segnala lo stato ("Strumenti: DISATTIVATI (JSON mode attivo)").

## Skill

Una skill e' un corpo di conoscenza specialistica (le convenzioni di un linguaggio, le
regole di un cliente, un tono di scrittura) che serve solo in alcune sessioni. Sta in
`skills/<nome>/SKILL.md`, con frontmatter `name` e `description`, e la cartella permette di
tenere accanto script ed esempi.

```
skills/
  wordpress/
    SKILL.md
```

Nel system prompt entrano sempre solo nome e descrizione delle skill disponibili: il corpo
si carica con `/skill <nome>` e resta attivo per la sessione, `/skill off` lo rimuove. Le
skill si cercano nella cartella di lavoro e in `~/.config/ernesto/skills/`, che valgono in
ogni progetto.

**Skill o playbook?** Un playbook (`playbooks/`) e' una *procedura* che il modello legge da
se' quando riconosce l'attivita'; una skill e' *conoscenza* che attivi tu e che influenza
tutte le risposte della sessione.

## Configurazione: `config.yaml`

Copia `context/config.yaml` nella cartella di lavoro del progetto (o lascia quello globale
in `~/.config/ernesto/context/`) per impostare il modello iniziale, il modello usato per i riassunti
della compattazione e i pattern pericolosi aggiuntivi. Vince il primo file trovato; tutte
le chiavi sono opzionali e un file malformato viene ignorato senza bloccare l'avvio.

## Uso non presidiato

Con `--prompt "testo"` ernesto esegue un solo turno e termina, quindi può stare in cron o
nell'Utilità di pianificazione. Tre avvertenze:

- senza terminale interattivo **ogni conferma viene rifiutata**, quindi un task che tocca
  file o invia email si blocca: serve `--yolo`, e con `--yolo` la denylist non protegge più;
- vanno bene i compiti che leggono e riferiscono (rassegne stampa, controlli, riepiloghi),
  molto meno quelli che modificano progetti reali senza nessuno che guardi;
- prova sempre la riga di comando con `--dry-run` prima di metterla in pianificazione.

## Policy di sicurezza

- **Sandbox filesystem**: per `list_files`, `read_file`, `write_file` e `edit_file`
  ogni path è risolto con `realpath` e deve restare dentro la cartella di lavoro,
  sempre (anche con `--yolo`). **`run_command` non è sandboxato**: esegue una shell
  arbitraria con la sola `cwd` sulla workdir, quindi un comando può scrivere ovunque
  l'utente abbia permessi. La difesa lì è la conferma, non un confine: i percorsi
  assoluti e le risalite con `..` fanno scattare una richiesta di conferma (euristica
  sul testo del comando, aggirabile: serve contro la disattenzione, non contro un
  modello che voglia eluderla).
- **Posta in arrivo**: leggere ed elencare non chiede conferma, spostare nel cestino sì,
  con etichetta distruttiva, e la chiede anche `imap_move` quando la destinazione è il
  cestino, altrimenti sarebbe la scorciatoia per eliminare senza passare da `imap_delete`.
  Gli allegati si salvano solo su richiesta esplicita e il nome dichiarato nella email viene
  ripulito prima di passare, comunque, dalla sandbox. Il corpo di un messaggio arriva al
  modello incorniciato da un avviso: è testo scritto da terzi, quindi materiale da leggere e
  non istruzioni da eseguire. Con `--yolo` quella cornice resta ma le conferme no: una
  casella aperta e nessuna conferma è la combinazione da evitare.
- **Conferme**: prima di `send_email` e di comandi che matchano la denylist
  (`rm -rf`, `sudo`, `git push`, `git reset --hard`, `docker system prune`, …)
  viene chiesta conferma, con etichetta e colore diversi a seconda della gravità
  (distruttivo, esterno, attenzione). Il comando è normalizzato prima del confronto, così
  `rm -r -f` e `RM -RF` non sfuggono; resta comunque una difesa contro la disattenzione,
  non contro un modello che voglia eluderla. La denylist è estendibile in `config.yaml`
  (`safety.deny_patterns`, lista di regex).
- **`--yolo` / `/yolo`**: salta le conferme. Lo stato è sempre visibile nel prompt.
- **`--dry-run`**: nessun effetto collaterale, tutto simulato.
- **Segreti**: nessuna chiave nei sorgenti; i valori delle variabili d'ambiente
  non vengono mai stampati né loggati (mascherati nel log JSONL).

## Esempi d'uso

- *"Cerca sul web le novità di Qwen 3.8 e riassumile in 5 punti."*
- *"Scrivi uno script `stats.py` che calcola media e mediana di una lista e lancialo."*
- *"Invia una mail di test a me@esempio.com con oggetto 'prova ernesto'."*
- *"Clona il repo X in una sottocartella e dimmi com'è strutturato."*
- *"Leggi `context/identity.md` e dimmi quali comandi di test usa questo progetto."*

## Sviluppo

```bash
pytest tests/ -q          # test
ruff check ernesto/ tests/ ernesto.py   # lint
```

Struttura del codice:

```
ernesto.py            # entry point
ernesto/
  cli.py              # typer + REPL + comandi slash
  agent.py            # loop agentico (streaming + tool calls)
  models.py           # registry modelli + prezzi live
  context.py          # context/: soul.md, identity.md, credentials.md, indice memorie
  session.py          # stato, log JSONL, costi, compattazione storia
  config.py           # costanti, .env, config.yaml
  mcp_client.py       # integrazione MCP opzionale
  tools/              # registry + filesystem, shell, web, mail
tests/                # suite pytest
```

## Licenza

MIT — vedi [LICENSE](LICENSE).
