"""Test per il caricamento dei file di contesto e la verifica delle env vars."""

from __future__ import annotations

from pathlib import Path

import pytest

from ernesto.config import MEMORY_DIR
from ernesto.context import (
    AGENT_SYSTEM_PROMPT,
    compose_system_prompt,
    extract_env_vars,
    load_context,
    memory_files,
    parse_soul,
    reload_memory,
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
    assert summary_line(ctx) == "Contesto: soul.md ✗ · agent.md ✗ · credentials.md ✗ · memorie: 0"
    # Il system prompt di default resta composto comunque
    assert AGENT_SYSTEM_PROMPT in compose_system_prompt(ctx)


def test_context_files_present(workdir: Path) -> None:
    """I tre file presenti in workdir vengono caricati e riepilogati."""
    (workdir / "soul.md").write_text("Sei allegro.", encoding="utf-8")
    (workdir / "agent.md").write_text("Usa sempre pytest.", encoding="utf-8")
    (workdir / "credentials.md").write_text(CREDENTIALS_SAMPLE, encoding="utf-8")
    ctx = load_context(workdir)
    assert summary_line(ctx) == "Contesto: soul.md ✓ · agent.md ✓ · credentials.md ✓ · memorie: 0"
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


# ---------------------------------------------------------------------------
# memorie
# ---------------------------------------------------------------------------


def test_indice_memorie_nel_prompt_senza_contenuto(workdir: Path) -> None:
    """Il prompt elenca le memorie ma non ne carica il contenuto."""
    (workdir / "memory.md").write_text("# Preferenze\nIl cliente preferisce PostgreSQL.", encoding="utf-8")
    ctx = load_context(workdir)
    prompt = compose_system_prompt(ctx)
    assert "memory.md" in prompt
    assert "Preferenze" in prompt              # la prima riga fa da descrizione
    assert "PostgreSQL" not in prompt          # il contenuto resta fuori dal contesto
    assert "read_file" in prompt               # il modello sa come leggerla


def test_indice_memorie_senza_file(workdir: Path) -> None:
    """Senza memorie l'indice lo dichiara, cosi' il modello non le cerca invano."""
    prompt = compose_system_prompt(load_context(workdir))
    assert "Nessun file di memoria" in prompt


def test_memoria_di_sessione_dichiarata(workdir: Path) -> None:
    """Il nome del file di memoria della sessione corrente e' nel prompt."""
    ctx = load_context(workdir, session_memory="memories/memory-20260917_094311.md")
    prompt = compose_system_prompt(ctx)
    assert "memories/memory-20260917_094311.md" in prompt
    assert "QUESTA sessione" in prompt


def test_memorie_di_sessione_elencate_dalla_piu_recente(workdir: Path) -> None:
    """Le memorie di sessione compaiono nell'indice, dalla piu' recente."""
    memories = workdir / MEMORY_DIR
    memories.mkdir()
    (memories / "memory-20260101_100000.md").write_text("vecchia", encoding="utf-8")
    (memories / "memory-20260917_094311.md").write_text("recente", encoding="utf-8")
    elenco = [p.name for p in memory_files(workdir)]
    assert elenco == ["memory-20260917_094311.md", "memory-20260101_100000.md"]
    prompt = compose_system_prompt(load_context(workdir))
    assert prompt.index("memory-20260917_094311.md") < prompt.index("memory-20260101_100000.md")


def test_memorie_solo_dalla_workdir(workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Una memoria in ~/.config non deve rientrare negli altri progetti."""
    fake_config = tmp_path / "config-home"
    fake_config.mkdir()
    (fake_config / "memory.md").write_text("memoria di un altro progetto", encoding="utf-8")
    monkeypatch.setattr("ernesto.context.config_dir", lambda: fake_config)
    assert memory_files(workdir) == []


def test_reload_memory_rileva_i_cambiamenti(workdir: Path) -> None:
    """L'indice si aggiorna quando una memoria nasce o cambia dimensione."""
    ctx = load_context(workdir)
    assert reload_memory(ctx) is False
    (workdir / "memory.md").write_text("primo fatto", encoding="utf-8")
    assert reload_memory(ctx) is True
    assert reload_memory(ctx) is False
    (workdir / "memory.md").write_text("un fatto completamente diverso", encoding="utf-8")
    assert reload_memory(ctx) is True
    assert "memory.md" in ctx.memory_index


# ---------------------------------------------------------------------------
# fusione di agent.md
# ---------------------------------------------------------------------------


def test_agent_base_e_progetto_si_sommano(
    workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le istruzioni di base non spariscono quando il progetto ha il suo agent.md."""
    fake_config = tmp_path / "config-home"
    fake_config.mkdir()
    (fake_config / "agent.md").write_text("Regola generale: rispondi in italiano.", encoding="utf-8")
    (workdir / "agent.md").write_text("Regola di progetto: usa pytest.", encoding="utf-8")
    monkeypatch.setattr("ernesto.context.config_dir", lambda: fake_config)
    prompt = compose_system_prompt(load_context(workdir))
    assert "Regola generale" in prompt
    assert "Regola di progetto" in prompt
    # prima le regole di base, poi quelle del progetto, che possono specializzarle
    assert prompt.index("Regola generale") < prompt.index("Regola di progetto")


def test_agent_solo_di_base(workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza agent.md nel progetto valgono comunque le istruzioni di base."""
    fake_config = tmp_path / "config-home"
    fake_config.mkdir()
    (fake_config / "agent.md").write_text("Regola generale.", encoding="utf-8")
    monkeypatch.setattr("ernesto.context.config_dir", lambda: fake_config)
    assert "Regola generale." in compose_system_prompt(load_context(workdir))


def test_agent_non_duplicato_se_workdir_e_config_coincidono(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lanciando ernesto dentro ~/.config/ernesto il file non viene contato due volte."""
    (workdir / "agent.md").write_text("Regola unica.", encoding="utf-8")
    monkeypatch.setattr("ernesto.context.config_dir", lambda: workdir)
    assert compose_system_prompt(load_context(workdir)).count("Regola unica.") == 1
