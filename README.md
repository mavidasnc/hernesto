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

Opzioni (`python ernesto.py --help` per l'elenco completo):

| Opzione | Effetto |
|---|---|
| `--workdir PATH` | Cartella di lavoro (sandbox filesystem e cwd dei comandi) |
| `--model ID` | Modello iniziale (es. `moonshotai/kimi-k2.6`) |
| `--yolo` | Salta tutte le conferme di sicurezza (usare con cautela) |
| `--dry-run` | Simula write/edit/email/comandi senza toccare nulla |
| `--reasoning low\|medium\|high\|xhigh` | Livello di reasoning (default `medium`) |
| `--no-mcp` | Disabilita l'integrazione MCP |

## Configurazione: i file di contesto

All'avvio ernesto legge dalla cartella di lavoro (fallback `~/.config/ernesto/`)
i file markdown che definiscono identità, istruzioni, memoria e credenziali del progetto:

- **`soul.md`** — personalità e tono dell'assistente. Preposto al system prompt;
  con una riga frontmatter `mode: replace` lo sostituisce del tutto.
- **`agent.md`** — istruzioni operative del progetto (convenzioni, comandi di
  test/lint, vincoli). Aggiunto al system prompt dopo `soul.md`.
- **`credentials.md`** — dichiara quali variabili d'ambiente servono, a cosa
  servono e come ottenerle. **Non contiene valori reali**: le chiavi stanno
  nelle variabili d'ambiente (o in un `.env` locale, caricato come fallback e
  mai committato). All'avvio ernesto verifica che le variabili dichiarate
  esistano: `OPENROUTER_API_KEY` mancante è un errore fatale, le altre
  producono un avviso e il tool corrispondente risponde con un errore leggibile.
- **`memory.md`** — memoria di lavoro del progetto: fatti durevoli e decisioni che
  l'agente stesso scrive e pota con `edit_file`. Cercata **solo** nella cartella di
  lavoro (non in `~/.config/ernesto/`), riletta a ogni turno, troncata a 4000 caratteri
  perché il system prompt viaggia in ogni richiesta. Sopravvive a `/clear` e alle
  sessioni successive.

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

Copia `mcp.json.example` in `mcp.json` e configura i tuoi server stdio; richiede
`pip install mcp`. Se la libreria o un server non sono disponibili, ernesto
parte comunque con un avviso.

## Comandi interattivi

| Comando | Effetto |
|---|---|
| `/model` | Cambia il modello attivo (azzera la conversazione) |
| `/context` | Riepilogo del contesto: modello, reasoning, token, strumenti, stato |
| `/clear` | Azzera la conversazione (mantiene log e conteggi cumulativi) |
| `/compact` | Riassume subito i risultati strumento in storia (`/compact N` preserva N giri) |
| `/yolo` | Attiva/disattiva il bypass delle conferme |
| `/tools` | Elenca gli strumenti registrati (nativi + MCP) |
| `/log` | Percorso del log di sessione e riepilogo |
| `/cost` | Costo cumulativo della sessione |
| `/reasoning [livello]` | Mostra o cambia il livello di reasoning |
| `/save` | Salva l'intera sessione in `saves/` |
| `exit` / `quit` / Ctrl+C | Termina |

Il prompt mostra sempre i cumulativi di sessione: `Tu [24.1k in · 6.3k out · $0.0082]>`.

> **Nota — JSON mode e strumenti sono incompatibili.** Se attivi il JSON mode
> (alla selezione del modello con `/model`), gli strumenti vengono disattivati:
> `response_format: json_object` impedisce ai provider di emettere tool call
> native. Per usare gli strumenti lascia il JSON mode disattivato; `/context`
> segnala lo stato ("Strumenti: DISATTIVATI (JSON mode attivo)").

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
  viene chiesta conferma. La denylist è estendibile in `config.yaml`
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
- *"Leggi `agent.md` e dimmi quali comandi di test usa questo progetto."*

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
  context.py          # soul.md / agent.md / memory.md / credentials.md
  session.py          # stato, log JSONL, costi, compattazione storia
  config.py           # costanti, .env, config.yaml
  mcp_client.py       # integrazione MCP opzionale
  tools/              # registry + filesystem, shell, web, mail
tests/                # suite pytest
```

## Licenza

MIT — vedi [LICENSE](LICENSE).
