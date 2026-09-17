# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandi

```bash
.venv/Scripts/python -m pytest tests/ -q                       # tutta la suite
.venv/Scripts/python -m pytest tests/test_shell.py -q           # un file
.venv/Scripts/python -m pytest tests/test_shell.py::test_x -q   # un singolo test
.venv/Scripts/python -m ruff check ernesto/ tests/ ernesto.py   # lint
python ernesto.py --workdir PATH --model ID --dry-run           # avvio manuale
```

Su Linux/macOS sostituire `.venv/Scripts/` con `.venv/bin/`.
Per provare l'agente a mano senza effetti collaterali usare sempre `--dry-run`
(write/edit/email/comandi simulati); `--workdir` sposta sia la sandbox sia la cwd dei comandi.
Dopo ogni modifica al codice: test + lint prima di considerare il lavoro finito.

## Architettura

`ernesto` è un agente da terminale che parla con OpenRouter tramite il client OpenAI.

Flusso: `ernesto.py` → `ernesto/cli.py` (`main`, typer + REPL + comandi slash) →
`ernesto/agent.py` (`run_turn`).

`run_turn` è il loop agentico: chiama l'API in streaming, accumula le tool call parziali
per `index` (`_consume_stream`), le esegue, riaccoda i messaggi `role: "tool"` e ricicla
fino a una risposta senza tool call, con guard rail `MAX_AGENT_STEPS` (30). In caso di
errore API, di `KeyboardInterrupt` o di provider che non supporta i tool, la storia viene
riavvolta a `rewind_index` (l'ultimo messaggio utente) invece di restare inconsistente.

`SessionState` (`ernesto/session.py`) è lo stato condiviso: messaggi, flag
(`json_mode`, `yolo`, `dry_run`, `tools_enabled`), cumulativi di token e costo, logger.
Viene **iniettato in ogni strumento** al momento della costruzione: è così che i tool
conoscono la workdir della sandbox e i flag di sicurezza. Non esiste stato globale.

Il system prompt è composto da `ernesto/context.py` (`load_context` →
`compose_system_prompt`): prompt di base + `soul.md` + `identity.md` + `credentials.md`,
cercati in `context/` prima della workdir e poi di `~/.config/ernesto/` (costante
`CONTEXT_DIR`), più l'**indice delle memorie**. `identity.md` è l'unico file che si somma
invece di essere sostituito (`identity_base` dalla config dir più quello del progetto):
serve perché le regole di base valgano anche in un progetto che ha il suo `identity.md`.
I file di base versionati stanno in `context-base/` e si installano con
`install-context.py`; `context/` nel repo è invece il contesto del progetto ernesto.
`.env` e le memorie restano fuori da `context/`.
Le memorie (`memory.md` persistente e `memories/memory-<ts>.md` di sessione) non entrano
mai nel prompt: `memory_index()` ne elenca nome, dimensione e prima riga, e il modello
legge il contenuto con `read_file` solo quando serve. `refresh_system_prompt()` ricalcola
l'indice una volta per turno nel REPL, mai dentro il ciclo di step, che distruggerebbe il
prompt caching del provider.

Le preferenze utente stanno in `config.yaml` (workdir, poi `~/.config/ernesto/`), letto da
`load_user_config()`/`config_section()` in `ernesto/config.py`: modello iniziale, modello
per i riassunti della compattazione, denylist aggiuntiva. È l'unico punto da estendere per
una nuova preferenza. `soul.md` con frontmatter
`mode: replace` sostituisce il prompt di base invece di accodarsi.

Gli strumenti stanno in `ernesto/tools/`: la classe base `Tool` e la factory
`build_native_tools(state, confirm_fn)` sono in `tools/__init__.py`, unico punto in cui
la lista attiva viene decisa. `tool_schemas()` converte i tool negli schema OpenAI.
Gli strumenti MCP (opzionali, `ernesto/mcp_client.py`, config `mcp.json`) si aggiungono
alla stessa lista con nome `mcp__<server>__<tool>`; se la libreria `mcp` o un server
mancano, la sessione parte lo stesso con un avviso.

## Invarianti da non violare

- **Un tool non lancia mai.** `Tool.run()` restituisce sempre una stringa; gli errori
  diventano `"ERRORE: ..."` e tornano al modello come contenuto del messaggio tool.
- **Ogni path degli strumenti filesystem passa da `resolve_in_sandbox()`**
  (`tools/filesystem.py`): risoluzione con `realpath`, quindi anche i symlink che escono
  dalla workdir vengono respinti, sempre, anche con `--yolo`. **`run_command` è fuori da
  questa garanzia**: esegue una shell arbitraria e può scrivere ovunque. Lì la difesa è
  `find_escaping_path()` in `tools/shell.py`, che chiede conferma su percorsi assoluti e
  `..`: euristica sul testo del comando, non un confine.
- **Le conferme dichiarano la gravità** (`LEVEL_DESTRUCTIVE`/`LEVEL_EXTERNAL`/
  `LEVEL_WARNING` in `tools/__init__.py`): le etichette sono ASCII e il colore si applica
  solo se `sys.stdout.isatty()`, come per il banner.
- **La compattazione riscrive `content`, non rimuove mai messaggi**
  (`compact_tool_results` in `session.py`): così le coppie assistant-con-`tool_calls` /
  `tool` restano accoppiate e `rewind_index` in `run_turn` resta valido.
- **JSON mode e `tools` non vanno mai inviati insieme.** Con
  `response_format: json_object` alcuni provider descrivono la tool call in JSON testuale
  invece di eseguirla; `run_turn` omette i `tools` quando `json_mode` è attivo, e ci sono
  test di regressione su entrambi i rami.
- **Cartelle generate → `NOISE_DIRS`** (`tools/filesystem.py`): una ricorsione di
  `list_files` che le includa inietta migliaia di token di rumore in *ogni* step del loop.
- **Segreti mai in chiaro**: `SessionLogger` maschera i valori noti nel JSONL; niente
  valori di credenziali in stdout.
- Comandi pericolosi: denylist regex in `DEFAULT_DENY_PATTERNS` (`config.py`), estendibile
  da `config.yaml` (`safety.deny_patterns`), applicata da `find_deny_match()` in
  `tools/shell.py`; il match richiede conferma tramite `confirm_fn`.

## Estendere

**Nuovo modello**: una riga `ModelConfig` in `MODELS` (`ernesto/models.py`);
`json_supported` = `response_format` presente in `supported_parameters` su
`GET /api/v1/models`, `schema_supported` = `structured_outputs`. I prezzi arrivano a
runtime da `load_pricing()`.

**Nuovo strumento**: una classe in `ernesto/tools/` con `name`, `description`,
`parameters` (JSON schema) e `run(**kwargs) -> str`, più una riga in
`build_native_tools()`. Se ha effetti collaterali, accettare `confirm_fn` e rispettare
`state.dry_run`.

## Convenzioni

Identificatori e codice in inglese; docstring, commenti e messaggi utente in italiano.
Type hints ovunque, `from __future__ import annotations`, import dei tipi sotto
`TYPE_CHECKING`. Ruff con riga a 120 e regole `E,F,W,I,UP,B,SIM,RUF` (`pyproject.toml`).
Ogni cambiamento rilevante va annotato in `CHANGELOG.md` (Keep a Changelog, in italiano).

## Cosa non è codice applicativo

- `soul.md`, `agent.md`, `credentials.md`: input **runtime di ernesto**, non istruzioni
  per Claude Code. Modificarli cambia il comportamento dell'agente, non il tuo.
- `docs/`, `ernesto-esN-prompt.md`, `esN/`: benchmark a 5 esercizi
  (fixture → prompt → verifica → scorecard), vedi `docs/ernesto-benchmark-README.md`.
- `logs/`, `saves/`: output di sessione, ignorati da git.
