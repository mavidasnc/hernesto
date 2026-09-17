"""Test della configurazione utente (config.yaml) e del modello di default."""

from __future__ import annotations

from pathlib import Path

import pytest

from ernesto.config import CONTEXT_DIR, config_section, load_deny_patterns, load_user_config
from ernesto.models import DEFAULT_MODEL, find_model

CONFIG_SAMPLE = """model:
  default: qwen/qwen3.8-27b
  json_mode: false
compact:
  summary_model: google/gemini-2.5-flash
  llm_summary: true
safety:
  deny_patterns:
    - "shutdown"
"""


def _ctx(base: Path) -> Path:
    """La sottocartella context/ di una base, creata al volo per i test."""
    d = base / CONTEXT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _cache_pulita() -> None:
    """La cache di config.yaml e' per processo: va svuotata fra un test e l'altro."""
    from ernesto import config

    config._user_config_cache.clear()


def test_config_assente_non_e_un_errore(workdir: Path) -> None:
    """Senza config.yaml si parte lo stesso, con tutte le sezioni vuote."""
    assert load_user_config(workdir) == {}
    assert config_section(workdir, "model") == {}


def test_config_letta_dalla_workdir(workdir: Path) -> None:
    """Le sezioni dichiarate vengono lette."""
    (_ctx(workdir) / "config.yaml").write_text(CONFIG_SAMPLE, encoding="utf-8")
    assert config_section(workdir, "model")["default"] == "qwen/qwen3.8-27b"
    assert config_section(workdir, "compact")["summary_model"] == "google/gemini-2.5-flash"
    assert config_section(workdir, "compact")["llm_summary"] is True


def test_config_malformata_viene_ignorata(workdir: Path) -> None:
    """Uno YAML rotto non impedisce l'avvio: si continua con i default."""
    (_ctx(workdir) / "config.yaml").write_text("model: [non chiusa\n  :", encoding="utf-8")
    assert load_user_config(workdir) == {}


def test_deny_patterns_estesi_da_config(workdir: Path) -> None:
    """I pattern di config.yaml si aggiungono a quelli di default, non li sostituiscono."""
    (_ctx(workdir) / "config.yaml").write_text(CONFIG_SAMPLE, encoding="utf-8")
    patterns = load_deny_patterns(workdir)
    assert "shutdown" in patterns
    assert any("sudo" in p for p in patterns)


def test_modello_di_default() -> None:
    """Il default del registry e' Qwen 3.8 27B e il suo ID esiste davvero."""
    assert DEFAULT_MODEL.id == "qwen/qwen3.8-27b"
    assert find_model(DEFAULT_MODEL.id) is DEFAULT_MODEL
