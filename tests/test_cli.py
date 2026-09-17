"""Test dell'interfaccia: elenco comandi, completamento e coerenza col dispatcher."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from prompt_toolkit.document import Document

from ernesto.cli import COMMANDS, _CommandCompleter, handle_command


def test_ogni_comando_ha_una_descrizione() -> None:
    """Nessuna voce senza descrizione: l'elenco e' anche l'aiuto."""
    for nome, descrizione in COMMANDS:
        assert nome.startswith("/")
        assert len(descrizione) > 10


def test_commands_e_dispatcher_coincidono() -> None:
    """COMMANDS e handle_command non possono divergere in silenzio."""
    sorgente = inspect.getsource(handle_command)
    gestiti = {riga.split('"')[1] for riga in sorgente.splitlines() if 'command == "' in riga}
    elencati = {nome for nome, _ in COMMANDS}
    assert gestiti == elencati, f"solo nel dispatcher: {gestiti - elencati}; solo in COMMANDS: {elencati - gestiti}"


def _proposte(testo: str) -> list[str]:
    completer = _CommandCompleter()
    document = Document(testo, len(testo))
    return [c.text for c in completer.get_completions(document, SimpleNamespace())]


def test_completer_propone_tutti_i_comandi_con_lo_slash() -> None:
    """Digitando `/` si vedono tutti i comandi."""
    assert set(_proposte("/")) == {nome for nome, _ in COMMANDS}


def test_completer_filtra_mentre_si_digita() -> None:
    """Il prefisso restringe le proposte."""
    assert _proposte("/co") == ["/context", "/command", "/compact", "/cost"]
    assert _proposte("/conte") == ["/context"]


def test_completer_muto_sul_testo_normale() -> None:
    """Un messaggio all'agente non attiva il completamento."""
    assert _proposte("leggi il file") == []
