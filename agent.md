# agent.md — istruzioni operative del progetto

## Progetto
Questo repository contiene **ernesto**, un agente da terminale in Python (3.10+)
che parla con i modelli LLM via OpenRouter e dispone di strumenti per filesystem,
shell, ricerca web, email e MCP.

## Convenzioni
- Codice e identificatori in inglese; docstring, commenti e messaggi utente in italiano.
- Type hints ovunque; lint con `ruff`.
- Ogni strumento è una classe in `ernesto/tools/` con `name`, `description`,
  `parameters` (JSON schema) e `run(**kwargs) -> str` che non lancia mai eccezioni
  verso il modello: converte gli errori in stringhe `"ERRORE: ..."`.

## Comandi utili
- Test: `.venv/Scripts/python -m pytest tests/ -q` (Linux/macOS: `.venv/bin/python -m pytest tests/ -q`)
- Lint: `.venv/Scripts/python -m ruff check ernesto/ tests/ ernesto.py`
- Avvio: `python ernesto.py` (o `python -m ernesto`)

## Vincoli
- Il sandbox filesystem vale sempre: nessuna scrittura fuori dalla cartella di lavoro.
- Nessuna credenziale hardcoded nei sorgenti: solo variabili d'ambiente (vedi `credentials.md`).
- Dopo ogni modifica al codice, esegui test e linter prima di considerare il lavoro finito.
