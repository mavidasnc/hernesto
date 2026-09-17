# Prompt per Kimi Code — chat.py esteso in agente da terminale

## Contesto

Ho già uno script Python funzionante, `chat.py` (in allegato), una CLI di chat interattiva con OpenRouter. Lo uso come terminale REPL per parlare con vari modelli LLM. Ora voglio trasformarlo in un **agente da terminale** con accesso al filesystem, agli strumenti CLI della macchina, alla ricerca web e all'invio di email, mantenendo intatte tutte le funzionalità esistenti.

Lo script deve continuare a funzionare da riga di comando su Linux/macOS, Python 3.10+.

All'avvio, lo script deve **leggere automaticamente dalla cartella in cui viene lanciato** tre file di contesto (se presenti): `soul.md`, `agent.md` e `credentials.md`. In questo modo ogni cartella di progetto porta con sé la propria identità dell'agente, le proprie istruzioni operative e le indicazioni sulle credenziali da usare, senza bisogno di un file `.env` globale. I tre file vengono inviati tutti come contesto al modello e sono liberamente leggibili e scrivibili dagli strumenti filesystem.

## Funzionalità ESISTENTI da preservare invariati

- Registry dei modelli (`MODELS: list[ModelConfig]`) con selezione via `/model`, prezzi caricati a runtime da `GET /api/v1/models`.
- Streaming delle risposte con `stream_options={"include_usage": True}` e stampa del costo dopo ogni risposta.
- Comandi `/model` (con reset conversazione e richiesta JSON mode), `/save`, `exit`/`quit`, Ctrl+C.
- Gestione errori API (`APIStatusError`, `APIConnectionError`, `APIError`) con ripristino dello stato (`messages.pop()`).
- Verifica all'avvio delle credenziali richieste (dichiarate in `credentials.md`) contro le variabili d'ambiente (sostituisce il vecchio `.env`, vedi sezione dedicata).
- System prompt in italiano, messaggi utente in italiano.

## Obiettivi

Trasforma `chat.py` in un agente che, oltre a chiacchierare, può:

1. **Leggere e scrivere file nella cartella di lavoro** (e sue sottocartelle).
2. **Eseguire comandi CLI già presenti sulla macchina** (es. script Python, `pip`, `git`, `php`, `docker`, `pytest`, `ruff`, qualsiasi binario in `$PATH`).
3. **Cercare online** tramite l'API Brave Search.
4. **Inviare email** tramite l'API Resend.
5. **Integrare strumenti MCP opzionali** (server stdio configurabili) per estendere le capacità senza modificare il codice.
6. **Registrare tutto** in un log di sessione completo (JSONL) con contabilità dei costi cumulativa.

## File di contesto letti all'avvio

All'avvio, per ciascuno di questi file: cerca prima nella cartella di lavoro (o `--workdir`), poi in `~/.config/chat_cli/` come fallback. Se presente, viene caricato; se assente, si procede senza (eventualmente con un avviso per `credentials.md` se le chiavi mancano del tutto). All'avvio mostra una riga di riepilogo tipo: `Contesto: soul.md ✓ · agent.md ✓ · credentials.md ✓`.

### `soul.md` — personalità

Testo libero (markdown) che definisce la personalità, il tono e le regole generali dell'assistente per QUESTO progetto. Il suo contenuto viene preposto al system prompt di default (o lo sostituisce del tutto se contiene una riga frontmatter `mode: replace`, altrimenti `mode: append` di default).

### `agent.md` — istruzioni operative

Istruzioni operative specifiche del progetto: convenzioni di codice, comandi di test/lint da preferire, strutture di cartelle da rispettare, vincoli del dominio. Viene aggiunto al system prompt dopo `soul.md`, separato da un'intestazione `## Istruzioni operative del progetto`.

### `credentials.md` — gestione delle credenziali

File markdown che spiega **quali credenziali usa il progetto, dove vivono e come gestirle**. Per ogni credenziale: nome della variabile d'ambiente (in inline code), a cosa serve, come ottenerla/ruotarla, e le regole d'uso per l'agente. **I valori reali NON stanno in questo file**: restano nelle variabili d'ambiente della macchina. Esempio:

```markdown
# Credenziali — progetto demo

## OPENROUTER_API_KEY
- A cosa serve: routing verso i modelli LLM (obbligatoria).
- Dove vive: variabile d'ambiente; esportala in ~/.bashrc o lancia con `env`.
- Come ottenerla: https://openrouter.ai/keys
- Regole per l'agente: non stamparla mai, non copiarla in file committati.

## BRAVE_API_KEY
- A cosa serve: ricerca web (opzionale, abilita lo strumento brave_search).

## RESEND_API_KEY
- A cosa serve: invio email (opzionale, abilita lo strumento send_email).

## RESEND_FROM
- Indirizzo mittente per Resend, es. `Mavida Chat <chat@mavida.com>`.
```

Regole:
- `credentials.md` fa parte del contesto mandato al modello come gli altri due file e **deve essere leggibile e scrivibile dagli strumenti `read_file`/`write_file` come qualsiasi altro file**: l'agente lo consulta per sapere quali credenziali servono e come usarle, e può aggiornarlo quando le esigenze del progetto cambiano (es. aggiungere una nuova integrazione).
- A startup lo script analizza `credentials.md`, estrae i nomi delle variabili d'ambiente richieste (pattern: nomi in maiuscolo con `_KEY`/`_FROM`/simili, es. da inline code o da una sezione "Variabili richieste") e verifica che siano presenti in `os.environ`:
  - `OPENROUTER_API_KEY` mancante → errore fatale con messaggio che punta a `credentials.md` per le istruzioni;
  - chiavi opzionali mancanti (`BRAVE_API_KEY`, `RESEND_API_KEY`, `RESEND_FROM`) → avviso non fatale, strumento corrispondente registrato ma che restituisce errore leggibile se invocato.
- I **valori reali** delle env vars non vanno mai stampati né loggati nel JSONL: se un tool result o una risposta contiene una chiave, mascherarla (`sk-or-…abcd`) prima di loggarla.

## Architettura richiesta

Ristruttura lo script come pacchetto (non un unico file monolitico). Struttura proposta:

```
chat_cli/
  __init__.py
  __main__.py            # entry point: python -m chat_cli
  config.py              # caricamento credentials.md, config.yaml, mcp.json, costanti
  models.py              # ModelConfig + registry + load_pricing() (dal vecchio chat.py)
  session.py             # SessionState, log JSONL, conteggio costi cumulativo
  tools/
    __init__.py          # registro strumenti, decoratore @tool, generazione JSON schema
    base.py              # classe Tool: name, description, parameters (pydantic o TypedDict), run()
    filesystem.py        # list_files, read_file, write_file, edit_file
    shell.py             # run_command
    web.py               # brave_search
    mail.py              # send_email
  mcp_client.py          # client MCP opzionale (stdio), discovery tool a startup
  context.py             # caricamento soul.md / agent.md / credentials.md, composizione system prompt
  agent.py               # il loop agentico (vedi sotto)
  cli.py                 # REPL, comandi slash, streaming (typer per gli argomenti, questionary per conferme/menù)
```

L'entry point `python chat.py` deve continuare a funzionare (un piccolo shim che chiama `chat_cli.__main__`). Se preferisci mantenere tutto in un singolo `chat.py` organizzato in sezioni ben commentate, è accettabile, ma il registry strumenti e il client MCP devono comunque essere moduli logici separati e testabili.

## Il loop agentico (core)

1. L'utente scrive un messaggio; viene aggiunto a `state.messages`.
2. Si chiama `client.chat.completions.create(model, messages, tools=TOOLS, stream=True, stream_options={"include_usage": True}, extra_body={"reasoning": {"effort": state.reasoning_effort}})`.
3. **Streaming con tool calls**: gli `assistant` delta possono contenere `tool_calls`. Accumula gli delta normali stampandoli in tempo reale (come ora) e accumula le chiamate a strumenti chunk per chunk (campi `index`, `id`, `function.name`, `function.arguments` parziale da concatenare).
4. Quando il messaggio contiene `tool_calls`, NON rispondere subito all'utente: per ogni chiamata, verifica policy di sicurezza (vedi sotto), esegui lo strumento, stampa una riga compatta di log tipo `→ run_command("pytest -q") → exit 0` (o `→ brave_search("qwen 3.8 benchmark") → 10 risultati`), e appendi il risultato come messaggio `{"role": "tool", "tool_call_id": ..., "name": ..., "content": ...}`.
5. Rilancia la chiamata API con la storia aggiornata (ciclo). Termina quando il messaggio non contiene `tool_calls`; stampa la risposta finale, i token e il costo come ora.
6. **Guard rail sui turni**: parametro `MAX_AGENT_STEPS` (default 30) per interrompere loop infiniti, con messaggio chiaro all'utente.

## Token e costi sempre visibili

Oltre alla riga di usage dopo ogni risposta (feature esistente), i conteggi devono essere **visibili in permanenza**:

- **Prompt indicator**: il prompt di input mostra i cumulativi di sessione, es. `Tu [24.1k in · 6.3k out · $0.0082]> ` (usa `input()` con il prompt ricostruito a ogni iterazione; formatta con k/M sopra le migliaia).
- **Durante il loop agentico**, dopo ogni step del modello (compresi quelli con solo tool calls, dove oggi non si stampa nulla), aggiorna un riepilogo a fine step: `step 3/30 · +1.2k in · +340 out · run_command → exit 0`.
- Quando lo streaming è attivo e l'API non restituisce usage fino all'ultimo chunk, i conteggi si aggiornano al termine dello step — va bene, ma la riga di step va stampata comunque con i dati dell'ultimo chunk disponibile.
- Stima locale dei token in contesto (somma `len` euristica o `tiktoken` se installato, altrimenti stima caratteri/4) usata anche da `/context`.

## Interfaccia: typer e questionary

Valutazione richiesta e decisione attesa:

- **typer**: sì, per gli argomenti di lancio (sostituisce `argparse` o parametri hardcoded): `chat.py [--workdir PATH] [--model ID] [--yolo] [--dry-run] [--reasoning low|medium|high|xhigh] [--no-mcp]`. Documentare con `--help` completo in italiano.
- **questionary**: sì, per tutte le interazioni confermative (conferme di sicurezza, selezione modello in `/model`, scelta iniziale se `credentials.md` manca: "crearne uno ora?"), con default sensati e possibilità di rispondere da non-interattivo (se stdin non è un TTY, usare sempre i default).
- Il loop REPL principale resta su `input()` (più semplice e robusto del multiline); typer gestisce solo l'avvio, questionary solo le conferme.

## Strumenti da implementare

### Filesystem (`tools/filesystem.py`)

| Nome | Descrizione |
|---|---|
| `list_files` | `path` (relativo), `recursive: bool = False` → elenco file/cartelle con dimensione |
| `read_file` | `path`, `offset: int = 0`, `limit: int = 500` → contenuto testuale (contenuto binario: rifiuta con errore) |
| `write_file` | `path`, `content` → crea/sostituisci; crea directory intermedie; restituisce n. caratteri scritti |
| `edit_file` | `path`, `old_string`, `new_string`, `replace_all: bool = false` → sostituzione esatta (come una edit chirurgica); errore se `old_string` non trovata o non univoca (a meno di `replace_all`) |

**Sandbox obbligatoria**: ogni path viene risolto con `os.path.realpath` e deve restare dentro la cartella di lavoro (quella da cui è lanciato lo script, sovrascrivibile con `--workdir`). Path che escono (`../`, symlink) → errore restituito allo strumento, mai un'eccezione non gestita.

### Shell (`tools/shell.py`)

| Nome | Parametri | Note |
|---|---|---|
| `run_command` | `command: str`, `timeout: int = 120` | esegue via `sub subprocess.run(command, shell=True, cwd=workdir, capture_output=True, text=True, timeout=timeout)`; restituisce exit code + stdout + stderr concatenati, troncati a 8000 caratteri (con nota di troncamento) |

### Ricerca web (`tools/web.py`)

| Nome | Parametri | Note |
|---|---|---|
| `brave_search` | `query: str`, `count: int = 10` | `GET https://api.search.brave.com/res/v1/web/search` con header `X-Subscription-Token: $BRAVE_API_KEY`; restituisce per ogni risultato: titolo, url, snippet (testo), fino a `count` risultati |

Se `BRAVE_API_KEY` manca: lo strumento restituisce un errore leggibile che spiega come configurarlo, e NON viene registrato nel registry (o viene registrato ma risponde errore — scegli un comportamento e documentalo).

### Email (`tools/mail.py`)

| Nome | Parametri | Note |
|---|---|---|
| `send_email` | `to: str`, `subject: str`, `text: str`, `from_name: str = "Chat CLI"` | Invio via Resend: `POST https://api.resend.com/emails` con header `Authorization: Bearer $RESEND_API_KEY`; body JSON: `{"from": f"{from_name} <{RESEND_FROM}>", "to": [to], "subject": subject, "text": text}`. `RESEND_FROM` da env (es. `Mavida Chat <chat@mavida.com>`). Restituisce id del messaggio o errore API. |

### MCP opzionale (`mcp_client.py`)

- File di configurazione `mcp.json` cercato in `./mcp.json` poi `~/.config/chat_cli/mcp.json`:
  ```json
  {
    "mcpServers": {
      "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/percorso/permesso"] },
      "sqlite":     { "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "data.db"] }
    }
  }
  ```
- Se la libreria Python `mcp` è installata (`pip install mcp`): avvia i server in stdio, chiama `tools/list` a startup, registra ogni strumento come `mcp__<server>__<tool>` e lo rende disponibile al modello con il suo JSON schema.
- Se `mcp` non è installata o un server non parte: warning non fatale e continua senza quegli strumenti.
- I tool MCP vanno eseguiti tramite `tools/call` con timeout di 60s e risultato troncato a 8000 caratteri, come gli strumenti nativi.

## Policy di sicurezza e conferme

1. **Conferma interattiva** (chiedere sì/no) prima di eseguire:
   - `send_email` (mostrare destinatario, oggetto e anteprima del corpo);
   - `run_command` che matchano pattern pericolosi: `rm -rf`, `sudo`, `git push`, `git reset --hard`, `docker system prune`, `:(){ :|:& };:` o qualsiasi comando in una denylist configurabile (`config.yaml` → `safety.deny_patterns`, lista di regex).
2. Flag `--yolo` all'avvio (typer) e comando `/yolo` a runtime: stesso flag `state.yolo`, salta tutte le conferme. Da usare con cautela: avviso all'attivazione e indicazione nello stato (`/context` e prompt indicator mostrano `YOLO` quando attivo).
3. Il sandbox filesystem vale SEMPRE, anche con `--yolo`. `credentials.md` è un file di contesto normale: gli strumenti lo leggono e lo scrivono liberamente (contiene istruzioni, non segreti). Ciò che non si espone mai sono i **valori** delle variabili d'ambiente.
4. Nessuna password o API key hardcoded nei sorgenti: le chiavi arrivano solo da env vars (i cui nomi e le cui regole d'uso sono documentati in `credentials.md`), mai loggate in chiaro.
5. Modalità **dry-run** globale via `--dry-run`: `write_file`, `edit_file` e `send_email` restituiscono "simulato" senza toccare nulla, `run_command` non viene eseguito. Utile per testare prompt pericolosi.

## Nuovi comandi interattivi

| Comando | Effetto |
|---|---|
| `/context` | riepilogo del contesto attuale: modello, reasoning effort, stima token occupati dai messaggi di sistema (con provenienza: default / soul.md / agent.md / credentials.md), n. messaggi in storia, strumenti registrati (nativi + MCP), stato yolo/dry-run, percorso log |
| `/clear` | azzera la conversazione (mantiene il log su file, i conteggi cumulativi e i file di contesto caricati) |
| `/yolo` | toggle a runtime del bypass delle conferme: mostra lo stato attuale e, su cambio, stampa un avviso ("conferme disattivate: il modello eseguirà comandi e invii senza chiedere") |
| `/tools` | elenca gli strumenti registrati (nativi + MCP) con descrizione breve |
| `/log` | mostra percorso del file di log della sessione e riepilogo: n. messaggi, n. tool call eseguiti, token in/out totali, costo cumulativo |
| `/cost` | costo cumulativo della sessione |
| `/reasoning [low|medium|high|xhigh]` | mostra o cambia il livello di reasoning inviato via `extra_body={"reasoning": {"effort": ...}}` (default `medium`) |
| `/save` | come prima, ma salva l'intera sessione (non solo l'ultima risposta) |
| `/model`, `exit`, `quit` | come prima |

## Log di sessione

- File `logs/session-YYYYMMDD_HHMMSS.jsonl` accanto allo script: una riga JSON per ogni evento (timestamp, tipo: user/assistant/tool, modello, id tool_call, contenuto troncato a 4000 caratteri nel log, token usage quando disponibile).
- Il percorso viene mostrato all'avvio e con `/log`.

## System prompt dell'agente

Aggiungi al system prompt (sempre in italiano):

> "Sei un assistente da terminale con accesso a strumenti. Lavori SOLO nella cartella corrente. Usa gli strumenti per leggere/scrivere file, eseguire comandi, cercare sul web e inviare email. Prima di operare su file o eseguire comandi, leggi/verifica quando necessario. Dopo ogni modifica al codice, verifica con gli strumenti appropriati (es. test o linter) se l'utente lo chiede o se è evidente che serve. Non inventare contenuti di file che non hai letto. Consulta `credentials.md` per sapere quali credenziali sono disponibili e come usarle: i valori stanno nelle variabili d'ambiente, non stamparli mai. Riassumi a fine task i file toccati e le azioni eseguite."

## Qualità del codice

- Type hints ovunque, docstring in italiano, messaggi utente in italiano.
- Ogni strumento è una classe con `name`, `description`, `parameters` (JSON schema) e metodo `run(**kwargs) -> str` che NON lancia eccezioni verso il modello: converte sempre errori in stringhe `"ERRORE: ..."` restituite come risultato del tool.
- Test con `pytest`: sandbox path traversal (3 casi), troncamento output, denylist, parsing degli `arguments` JSON malformati, comportamento tool con API key mancante, caricamento di `soul.md`/`agent.md`/`credentials.md` (presente/assente), verifica env vars estratte da `credentials.md` (tutte presenti / opzionale mancante con avviso / `OPENROUTER_API_KEY` mancante fatale), mascheramento dei valori nel log. Usare mock per le chiamate HTTP (Brave, Resend) e `unittest.mock` per subprocess.
- `ruff` pulito.
- Dipendenze in `requirements.txt` (o `pyproject.toml`): `openai`, `httpx`, `typer`, `questionary`, `mcp` (opzionale, documentato come extra). `python-dotenv` non serve più (sostituito da `credentials.md`), rimuoverlo.

## Deliverable

- Pacchetto installabile/eseguibile, `python chat.py` funzionante come prima per la sola chat (se nessuno strumento è invocato, il comportamento è identico al vecchio script).
- `pytest` verde.
- README.md in italiano: installazione, configurazione (soul.md / agent.md / credentials.md con template d'esempio, mcp.json), comandi, policy di sicurezza, esempi d'uso (cerca sul web e riassumi; scrivi uno script e lancialo; invia una mail di test; clona un repo e analizzalo).

## Criteri di accettazione

1. Avvio → `/tools` mostra filesystem, run_command, brave_search, send_email (+ eventuali MCP).
2. Prompt "crea un file hello.py con una funzione che somma due numeri e lancialo con python" → il file esiste, il comando gira, risposta finale riassume.
3. `../etc/passwd` come path → errore sandbox, nessuna eccezione.
4. `send_email` senza `RESEND_API_KEY` → errore leggibile, crash zero.
5. `rm -rf /tmp/prova` via run_command → chiede conferma; con `--yolo` o `/yolo` attivo no; con denylist configurata → rifiutato sempre.
6. Avvio in una cartella con `soul.md` + `agent.md` + `credentials.md` → riepilogo "Contesto: ✓ ✓ ✓", il system prompt riflette soul.md + agent.md, le chiavi funzionano; in una cartella vuota → avvio comunque riuscito con avvisi.
7. Il prompt mostra i cumulativi `in/out/$` dopo ogni risposta; anche uno step di solo tool call stampa la sua riga di step.
8. `/context` mostra provenienza e stima token del system prompt, storia, strumenti, stato yolo/dry-run.
9. `credentials.md` è leggibile e scrivibile da `read_file`/`write_file`; all'avvio, env vars opzionali mancanti → avviso, `OPENROUTER_API_KEY` mancante → errore fatale con rimando a `credentials.md`; i valori delle chiavi non compaiono mai nel log JSONL.
10. Tutti i comandi e feature del vecchio chat.py funzionano invariati.

---

## Note d'uso (non copiare in Kimi Code)

- Prima di incollare, allega il file `chat.py` attuale e personalizza gli esempi (email del mittente Resend, server MCP reali che usi).
- `credentials.md` è pensato per contenere solo istruzioni (nomi delle variabili, a cosa servono, regole d'uso), non valori reali: se ci incolli chiavi vere, mettilo in `.gitignore` e non condividerlo. Se il progetto è un repo git senza gitignore, chiedi a Kimi Code di crearne uno.
- `soul.md` e `agent.md` possono essere committati nel repo: sono la memoria del progetto e vanno bene sotto versione.
- I provider dietro OpenRouter non espongono tutti il tool calling: verifica su openrouter.ai che il modello scelto (es. `qwen/qwen3.8-27b`) abbia provider con supporto tools, altrimenti lo script deve degradare con un avviso ("questo provider non supporta strumenti") invece di fallire.
- Fai una prima prova con `--dry-run` e con il modello free (`google/gemma-4-31b-it:free`) per validare il loop senza spendere.
