# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandi

```bash
.venv/Scripts/python -m pytest tests/ -q                       # tutta la suite
.venv/Scripts/python -m pytest tests/test_shell.py -q           # un file
.venv/Scripts/python -m pytest tests/test_shell.py::test_x -q   # un singolo test
.venv/Scripts/python -m ruff check ernesto/ tests/ ernesto.py build_bundle.py   # lint
python ernesto.py --workdir PATH --model ID --dry-run           # avvio manuale
python build_bundle.py                                          # bundle autonomo in dist/
```

Su Linux/macOS sostituire `.venv/Scripts/` con `.venv/bin/`.
Per provare l'agente a mano senza effetti collaterali usare sempre `--dry-run`
(write/edit/email/comandi simulati); `--workdir` sposta sia la sandbox sia la cwd dei comandi.

## Flusso da seguire a ogni modifica del codice

Nessuna modifica è finita finché questi cinque passi non sono completi, nell'ordine:

1. **Test e lint**: `pytest tests/ -q` e `ruff check ernesto/ tests/ ernesto.py`, entrambi
   verdi. Le modifiche al comportamento portano con sé il loro test.
2. **Versione**: bump di `__version__` in `ernesto/__init__.py`, secondo il versionamento
   semantico (patch per le correzioni, minor per funzionalità nuove o cambi di struttura dei
   file, major per rotture dell'interfaccia).
3. **CHANGELOG.md**: voce sotto la nuova versione, in italiano, formato Keep a Changelog.
   Si descrive lo **stato finale**, non i passaggi intermedi: se una scelta è stata rifatta
   durante il lavoro, la voce racconta solo dove si è arrivati e perché.
4. **Documentazione**: `README.md` per ciò che cambia per chi usa ernesto, questo file per
   ciò che serve a chi lavora sul codice. Un comportamento nuovo non documentato non esiste.
5. **Commit e push**: messaggio in italiano che spiega il *perché* oltre al cosa, poi
   `git push`.

## Architettura

`ernesto` è un agente da terminale che parla con OpenRouter tramite il client OpenAI.

Flusso: `ernesto.py` → `ernesto/cli.py` (`main`, typer + REPL + comandi slash) →
`ernesto/agent.py` (`run_turn`).

`run_turn` è il loop agentico: chiama l'API in streaming, accumula le tool call parziali
per `index` (`_consume_stream`), le esegue, riaccoda i messaggi `role: "tool"` e ricicla
fino a una risposta senza tool call, con guard rail `state.max_steps` (predefinito
`MAX_AGENT_STEPS`, 30; regolabile con `--max-steps` e `/step`). In caso di
errore API, di `KeyboardInterrupt` o di provider che non supporta i tool, la storia viene
riavvolta a `rewind_index` (l'ultimo messaggio utente) invece di restare inconsistente.

`SessionState` (`ernesto/session.py`) è lo stato condiviso: messaggi, flag
(`json_mode`, `yolo`, `dry_run`, `tools_enabled`), cumulativi di token, costo e tempo
(`record_time`, alimentato dal `finally` di `run_turn` perché anche i turni interrotti
contino), logger.
Viene **iniettato in ogni strumento** al momento della costruzione: è così che i tool
conoscono la workdir della sandbox e i flag di sicurezza. Non esiste stato globale.

Il system prompt è composto da `ernesto/context.py` (`load_context` →
`compose_system_prompt`): prompt di base + `soul.md` + `identity.md` + `credentials.md`,
cercati in `context/` prima della workdir e poi di `~/.config/ernesto/` (costante
`CONTEXT_DIR`), più l'**indice delle memorie**. Tutti e tre i file si sommano con la stessa
regola (`_load_pair`): prima la copia globale, poi quella del progetto, così le regole di
base valgono anche dove il progetto ha le sue. Due copie identiche, o la stessa cartella
in entrambi i ruoli, vengono caricate una volta sola.
I file versionati stanno in `context/` e si installano con `install-context.py`, che
esclude dalla copia globale il blocco `solo-progetto` di `identity.md`; quando la workdir è
questo repo, `project_only_section()` carica dal file locale solo quel blocco, evitando di
ripetere le regole generali. Fuori da `context/` restano `.env`, `memories/` (memoria
persistente e di sessione) e `workspace/`, entrambe ignorate da git.
Le memorie (`memories/memory.md` persistente e `memories/memory-<ts>.md` di sessione) non entrano
mai nel prompt: `memory_index()` ne elenca nome, dimensione e prima riga, e il modello
legge il contenuto con `read_file` solo quando serve. `refresh_system_prompt()` ricalcola
l'indice una volta per turno nel REPL, mai dentro il ciclo di step, che distruggerebbe il
prompt caching del provider.

Le preferenze utente stanno in `context/config.yaml` (workdir, poi `~/.config/ernesto/`), letto da
`load_user_config()`/`config_section()` in `ernesto/config.py`: modello iniziale, modello
per i riassunti della compattazione, denylist aggiuntiva. È l'unico punto da estendere per
una nuova preferenza. `soul.md` con frontmatter
`mode: replace` sostituisce il prompt di base invece di accodarsi.

Gli strumenti stanno in `ernesto/tools/`: la classe base `Tool` e la factory
`build_native_tools(state, confirm_fn)` sono in `tools/__init__.py`, unico punto in cui
la lista attiva viene decisa. `tool_schemas()` converte i tool negli schema OpenAI.
Gli strumenti MCP (opzionali, `ernesto/mcp_client.py`, config `context/mcp.json`) si aggiungono
alla stessa lista con nome `mcp__<server>__<tool>`; se la libreria `mcp` o un server
mancano, la sessione parte lo stesso con un avviso.

## Interfaccia

I comandi slash sono definiti **una volta sola** in `COMMANDS` (`cli.py`): da lì nascono il
completamento del prompt, `/command` e l'aiuto, e un test verifica che l'elenco coincida con
i rami di `handle_command`. Il prompt usa `prompt_toolkit` tramite `make_reader()`, che
ricade su `input()` se il terminale non lo supporta: ogni nuova funzione del prompt deve
restare dentro quel fallback.

Le **skill** (`ernesto/skills.py`) sono conoscenza caricata su richiesta: `discover_skills`
legge solo i frontmatter di `skills/<nome>/SKILL.md` (workdir e config dir, il progetto
vince), `skills_index` mette nel prompt nome e descrizione, e i corpi entrano solo per le
skill in `SessionState.loaded_skills`, riletti da disco a ogni composizione del prompt.

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

- `context/soul.md`, `context/identity.md`, `context/credentials.md`: input **runtime di
  ernesto**, non istruzioni per Claude Code. Modificarli cambia il comportamento
  dell'agente, non il tuo.
- `playbooks/`: procedure per l'agente, lette su sua iniziativa.
- `build_bundle.py`: distribuzione, non runtime. Costruisce in `dist/` una copia autonoma
  con il Python embeddable di python.org per i computer senza interprete installato; il
  suo punto delicato e' il file `._pth` del runtime, che rimpiazza il calcolo di
  `sys.path` e va riscritto perche' comprenda il bundle e le sue librerie. I launcher del
  repository restano la strada normale: provano l'interprete del `.venv` e lo
  ricostruiscono quando non parte, per esempio perche' la cartella arriva da un altro
  computer.
- `logs/`, `saves/`, `memories/`, `workspace/`, `rassegne/`: output di sessione e dati
  dell'agente, ignorati da git.
