"""Test dell'interfaccia: elenco comandi, completamento e coerenza col dispatcher."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from prompt_toolkit.document import Document

from ernesto.cli import (
    COMMANDS,
    _CommandCompleter,
    cmd_step,
    compose_prompt,
    handle_command,
    resolve_json_mode,
)
from ernesto.config import MAX_AGENT_STEPS
from ernesto.models import ModelConfig


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


def test_skill_nel_completamento() -> None:
    """/skill compare fra i comandi proposti."""
    assert "/skill" in _proposte("/sk")


def test_prompt_file_da_solo(tmp_path: Path) -> None:
    """Con il solo --prompt-file il turno e' il contenuto del file."""
    f = tmp_path / "istruzioni.md"
    f.write_text("Analizza questo testo.", encoding="utf-8")
    assert compose_prompt(None, f) == "Analizza questo testo."


def test_prompt_file_precede_il_messaggio(tmp_path: Path) -> None:
    """Il file fa da contesto, il messaggio da istruzione: in quest'ordine."""
    f = tmp_path / "dati.md"
    f.write_text("riga uno\nriga due", encoding="utf-8")
    assert compose_prompt("riassumi", f) == "riga uno\nriga due\n\nriassumi"


def test_senza_file_il_prompt_resta_intatto() -> None:
    assert compose_prompt("ciao", None) == "ciao"
    assert compose_prompt(None, None) is None


def test_json_mode_dalla_riga_di_comando() -> None:
    """--json attiva il JSON mode anche quando config.yaml non dice niente."""
    modello = ModelConfig("Test", "test/model", json_supported=True, schema_supported=False)
    assert resolve_json_mode(flag=True, configured=False, model=modello) is True


def test_json_mode_predefinito_spento() -> None:
    """Senza --json e senza configurazione il JSON mode resta disattivo."""
    modello = ModelConfig("Test", "test/model", json_supported=True, schema_supported=False)
    assert resolve_json_mode(flag=False, configured=False, model=modello) is False


def test_json_mode_ignorato_dai_modelli_che_non_lo_supportano() -> None:
    """Chiederlo a un modello senza response_format non lo attiva: lo ignorerebbe o darebbe errore."""
    modello = ModelConfig("Test", "test/model", json_supported=False, schema_supported=False)
    assert resolve_json_mode(flag=True, configured=True, model=modello) is False


def _stato_step(max_steps: int = MAX_AGENT_STEPS) -> SimpleNamespace:
    return SimpleNamespace(max_steps=max_steps)


def test_step_cambia_il_limite() -> None:
    """/step con un numero alza o abbassa il guard rail del turno."""
    stato = _stato_step()
    cmd_step(stato, "60")
    assert stato.max_steps == 60


def test_step_rifiuta_valori_non_validi() -> None:
    """Testo non numerico o zero non toccano il limite in vigore."""
    stato = _stato_step(30)
    cmd_step(stato, "molti")
    cmd_step(stato, "0")
    cmd_step(stato, "-5")
    assert stato.max_steps == 30


def test_step_senza_argomento_non_cambia_niente() -> None:
    """Senza argomento il comando mostra soltanto il valore corrente."""
    stato = _stato_step(45)
    cmd_step(stato, "")
    assert stato.max_steps == 45
