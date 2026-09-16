"""Fixture condivise per i test di ernesto."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ernesto.context import load_context
from ernesto.models import DEFAULT_MODEL
from ernesto.session import SessionState


@pytest.fixture(autouse=True)
def isolated_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isola i test dal ~/.config/ernesto reale della macchina."""
    fake = tmp_path / "config-home"
    monkeypatch.setattr("ernesto.context.config_dir", lambda: fake)
    monkeypatch.setattr("ernesto.config.config_dir", lambda: fake, raising=False)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Cartella di lavoro temporanea per la sandbox."""
    work = tmp_path / "work"
    work.mkdir()
    return work


@pytest.fixture
def state(workdir: Path) -> SessionState:
    """SessionState di test senza logger."""
    session = SessionState(model=DEFAULT_MODEL, workdir=workdir, context=load_context(workdir))
    session.reset_messages()
    return session
