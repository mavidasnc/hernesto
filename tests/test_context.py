"""Test per il caricamento dei file di contesto e la verifica delle env vars."""

from __future__ import annotations

from pathlib import Path

from ernesto.context import (
    AGENT_SYSTEM_PROMPT,
    compose_system_prompt,
    extract_env_vars,
    load_context,
    parse_soul,
    summary_line,
    verify_env_vars,
)

CREDENTIALS_SAMPLE = """# Credenziali — progetto demo

## OPENROUTER_API_KEY
- A cosa serve: routing LLM (obbligatoria).

## BRAVE_API_KEY
- A cosa serve: ricerca web (opzionale, abilita `brave_search`).

## RESEND_API_KEY
- Invio email opzionale.

## RESEND_FROM
- Mittente, es. `Mavida Chat <chat@mavida.com>`.
"""


def test_no_context_files(workdir: Path) -> None:
    """In una cartella vuota i file risultano assenti e l'avvio prosegue."""
    ctx = load_context(workdir)
    assert ctx.soul.content is None
    assert ctx.agent.content is None
    assert ctx.credentials.content is None
    assert summary_line(ctx) == "Contesto: soul.md ✗ · agent.md ✗ · credentials.md ✗"
    # Il system prompt di default resta composto comunque
    assert AGENT_SYSTEM_PROMPT in compose_system_prompt(ctx)


def test_context_files_present(workdir: Path) -> None:
    """I tre file presenti in workdir vengono caricati e riepilogati."""
    (workdir / "soul.md").write_text("Sei allegro.", encoding="utf-8")
    (workdir / "agent.md").write_text("Usa sempre pytest.", encoding="utf-8")
    (workdir / "credentials.md").write_text(CREDENTIALS_SAMPLE, encoding="utf-8")
    ctx = load_context(workdir)
    assert summary_line(ctx) == "Contesto: soul.md ✓ · agent.md ✓ · credentials.md ✓"
    prompt = compose_system_prompt(ctx)
    assert "Sei allegro." in prompt
    assert "## Istruzioni operative del progetto" in prompt
    assert "Usa sempre pytest." in prompt
    assert CREDENTIALS_SAMPLE in prompt


def test_soul_mode_append(workdir: Path) -> None:
    """Mode append (default): soul.md e' preposto al prompt di default."""
    (workdir / "soul.md").write_text("Sei allegro.", encoding="utf-8")
    ctx = load_context(workdir)
    assert ctx.soul_mode == "append"
    prompt = compose_system_prompt(ctx)
    assert "Sei allegro." in prompt
    assert AGENT_SYSTEM_PROMPT in prompt
    assert prompt.index("Sei allegro.") < prompt.index(AGENT_SYSTEM_PROMPT)


def test_soul_mode_replace(workdir: Path) -> None:
    """Mode replace: soul.md sostituisce del tutto il prompt di default."""
    (workdir / "soul.md").write_text("---\nmode: replace\n---\nSolo questo.", encoding="utf-8")
    ctx = load_context(workdir)
    assert ctx.soul_mode == "replace"
    prompt = compose_system_prompt(ctx)
    assert "Solo questo." in prompt
    assert AGENT_SYSTEM_PROMPT not in prompt


def test_parse_soul_bare_mode_line() -> None:
    """Anche una riga `mode: replace` isolata (senza ---) viene riconosciuta."""
    content, mode = parse_soul("mode: replace\nCorpo del prompt.")
    assert mode == "replace"
    assert content == "Corpo del prompt."


def test_extract_env_vars() -> None:
    """Estrazione dei nomi MAIUSCOLO_CON_UNDERSCORE da intestazioni e inline code."""
    names = extract_env_vars(CREDENTIALS_SAMPLE)
    assert "OPENROUTER_API_KEY" in names
    assert "BRAVE_API_KEY" in names
    assert "RESEND_API_KEY" in names
    assert "RESEND_FROM" in names
    # testo libero in minuscolo non produce falsi positivi
    assert "brave_search" not in names


def test_verify_env_vars_all_present() -> None:
    """Tutte le variabili presenti: nessun mancante."""
    env = {
        "OPENROUTER_API_KEY": "sk-or-x",
        "BRAVE_API_KEY": "b",
        "RESEND_API_KEY": "r",
        "RESEND_FROM": "f",
    }
    check = verify_env_vars(extract_env_vars(CREDENTIALS_SAMPLE), env)
    assert check.fatal_missing == []
    assert check.optional_missing == []
    assert "OPENROUTER_API_KEY" in check.present


def test_verify_env_vars_optional_missing() -> None:
    """Una variabile opzionale mancante produce un avviso, non un errore fatale."""
    env = {"OPENROUTER_API_KEY": "sk-or-x"}
    check = verify_env_vars(extract_env_vars(CREDENTIALS_SAMPLE), env)
    assert check.fatal_missing == []
    assert "BRAVE_API_KEY" in check.optional_missing
    assert "RESEND_API_KEY" in check.optional_missing


def test_verify_env_vars_openrouter_missing_fatal() -> None:
    """OPENROUTER_API_KEY mancante e' fatale, anche senza credentials.md."""
    check = verify_env_vars(extract_env_vars(CREDENTIALS_SAMPLE), {"BRAVE_API_KEY": "b"})
    assert check.fatal_missing == ["OPENROUTER_API_KEY"]
    # e anche con credentials.md assente (lista vuota)
    check = verify_env_vars([], {})
    assert check.fatal_missing == ["OPENROUTER_API_KEY"]
