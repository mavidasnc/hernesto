# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/),
e il progetto aderisce al [Versionamento Semantico](https://semver.org/lang/it/).

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
