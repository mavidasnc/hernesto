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
- Opzionali: `BRAVE_API_KEY` (ricerca web), `RESEND_API_KEY` + `RESEND_FROM` (email)

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

Per lanciarlo da qualunque cartella ci sono `bin/ernesto.cmd` (e `bin/ernesto` per git bash
e WSL): usano il Python del `.venv` del repository e mantengono come cartella di lavoro
quella da cui li lanci. Aggiungi la cartella `bin` del repository al PATH, oppure copia il
`.cmd` in una cartella gia' nel PATH facendolo puntare a quello del repository.

Opzioni (`python ernesto.py --help` per l'elenco completo):

| Opzione | Effetto |
|---|---|
| `--workdir PATH` | Cartella di lavoro (sandbox filesystem e cwd dei comandi) |
| `--model ID` | Modello iniziale (es. `moonshotai/kimi-k2.6`) |
| `--yolo` | Salta tutte le conferme di sicurezza (usare con cautela) |
| `--dry-run` | Simula write/edit/email/comandi senza toccare nulla |
| `--reasoning low\|medium\|high\|xhigh` | Livello di reasoning (default `medium`) |
| `--no-mcp` | Disabilita l'integrazione MCP |
| `--prompt "testo"` | Esegue un solo turno e termina, senza REPL (per cron e script) |

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
| `send_email` | Invio email via Resend |
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
