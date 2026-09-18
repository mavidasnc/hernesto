"""Test per il loop agentico: parsing argomenti e gestione tool call."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

from ernesto.agent import run_tool_call, run_turn
from ernesto.config import COMPACT_THRESHOLD_TOKENS, MAX_AGENT_STEPS
from ernesto.models import ModelConfig
from ernesto.session import COMPACT_PREFIX, SessionState
from ernesto.tools import Tool


def _storia_con_tool(turni: int, content: str = "contenuto\n" * 40) -> list[dict]:
    """Giri assistant(tool_calls) + risultato tool, per i test di compattazione."""
    messages: list[dict] = []
    for t in range(turni):
        call = {"id": f"c{t}", "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}}
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        messages.append({"role": "tool", "tool_call_id": call["id"], "name": "read_file", "content": content})
    return messages


class EchoTool(Tool):
    name = "echo"
    description = "Restituisce il messaggio ricevuto."
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def run(self, message: str = "", **kwargs: object) -> str:
        return f"echo: {message}"


def test_malformed_json_arguments() -> None:
    """Argomenti JSON malformati producono un errore leggibile, nessun crash."""
    tool_call = {"id": "call_1", "function": {"name": "echo", "arguments": "{non json"}}
    result = run_tool_call({"echo": EchoTool()}, tool_call)
    assert result.startswith("ERRORE: argomenti JSON non validi")


def test_non_object_arguments() -> None:
    """Argomenti JSON validi ma non oggetto vengono rifiutati."""
    tool_call = {"id": "call_1", "function": {"name": "echo", "arguments": "[1, 2]"}}
    result = run_tool_call({"echo": EchoTool()}, tool_call)
    assert result.startswith("ERRORE: argomenti JSON non validi")


def test_unknown_tool() -> None:
    """Uno strumento sconosciuto produce un errore leggibile."""
    tool_call = {"id": "call_1", "function": {"name": "nope", "arguments": "{}"}}
    result = run_tool_call({}, tool_call)
    assert "sconosciuto" in result


def test_tool_executed() -> None:
    """Una tool call valida viene eseguita e restituisce il risultato."""
    tool_call = {"id": "call_1", "function": {"name": "echo", "arguments": '{"message": "ciao"}'}}
    result = run_tool_call({"echo": EchoTool()}, tool_call)
    assert result == "echo: ciao"


def test_tool_exception_caught() -> None:
    """Un'eccezione interna del tool viene convertita in stringa di errore."""

    class BoomTool(Tool):
        name = "boom"

        def run(self, **kwargs: object) -> str:
            raise RuntimeError("esploso")

    tool_call = {"id": "call_1", "function": {"name": "boom", "arguments": "{}"}}
    result = run_tool_call({"boom": BoomTool()}, tool_call)
    assert "esploso" in result


def _fake_client(captured: dict) -> SimpleNamespace:
    """Client OpenAI finto: registra i kwargs della chiamata e risponde 'ok'."""
    chunk = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        choices=[SimpleNamespace(delta=SimpleNamespace(content="ok", tool_calls=None))],
    )

    def create(**kwargs: object) -> list[SimpleNamespace]:
        captured.update(kwargs)
        return [chunk]

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _fake_state(json_mode: bool) -> SimpleNamespace:
    return SimpleNamespace(
        model=ModelConfig("Test", "test/model", json_supported=True, schema_supported=False),
        messages=[{"role": "user", "content": "ciao"}],
        reasoning_effort="medium",
        json_mode=json_mode,
        tools_enabled=True,
        logger=None,
        tool_calls_count=0,
        max_steps=MAX_AGENT_STEPS,
        record_usage=lambda *a: None,
        record_time=lambda *a: None,
        last_seconds=0.0,
        total_seconds=0.0,
        history_token_estimate=lambda: 0,
    )


def test_json_mode_disables_tools(capsys: object) -> None:
    """Con JSON mode attivo i tools NON vengono inviati: json_object e' incompatibile
    col tool calling (il modello emetterebbe JSON testuale invece di tool calls)."""
    captured: dict = {}
    run_turn(_fake_state(json_mode=True), _fake_client(captured), [EchoTool()])
    assert "tools" not in captured
    assert captured.get("response_format") == {"type": "json_object"}


def test_tools_sent_without_json_mode(capsys: object) -> None:
    """Senza JSON mode gli strumenti vengono inviati normalmente."""
    captured: dict = {}
    run_turn(_fake_state(json_mode=False), _fake_client(captured), [EchoTool()])
    assert "tools" in captured
    assert captured["tools"][0]["function"]["name"] == "echo"


def test_auto_compact_below_threshold_noop(state: SessionState) -> None:
    """Sotto soglia la storia arriva all'API identica: nessun cambiamento percepito."""
    state.messages.extend(_storia_con_tool(turni=6))
    prima = [str(m.get("content") or "") for m in state.messages]
    captured: dict = {}
    run_turn(state, _fake_client(captured), [EchoTool()])
    assert state.compacted_count == 0
    assert [str(m.get("content") or "") for m in captured["messages"]][: len(prima)] == prima


def test_auto_compact_triggers_above_threshold(state: SessionState) -> None:
    """Sopra soglia i risultati vecchi partono gia' riassunti."""
    state.messages.extend(_storia_con_tool(turni=8, content="x" * (COMPACT_THRESHOLD_TOKENS // 2)))
    captured: dict = {}
    run_turn(state, _fake_client(captured), [EchoTool()])
    assert state.compacted_count > 0
    assert state.compacted_tokens > 0
    assert any(COMPACT_PREFIX in str(m.get("content") or "") for m in captured["messages"])


def test_tempo_del_turno_registrato(state: SessionState) -> None:
    """Il turno misura quanto e' durato e lo somma al cumulativo di sessione."""
    state.messages.append({"role": "user", "content": "ciao"})
    run_turn(state, _fake_client({}), [EchoTool()])
    assert state.last_seconds > 0
    assert state.total_seconds == state.last_seconds


def test_tempo_registrato_anche_se_il_turno_si_interrompe(state: SessionState) -> None:
    """Ctrl+C durante lo streaming: il tempo speso resta nel cumulativo."""
    def create(**_kwargs: object) -> list:
        raise KeyboardInterrupt

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    state.messages.append({"role": "user", "content": "ciao"})
    run_turn(state, client, [EchoTool()])
    assert state.total_seconds > 0


def test_riga_finale_mostra_i_tempi(state: SessionState, capsys) -> None:
    """Accanto a token e costo compaiono durata del turno e totale di sessione."""
    state.messages.append({"role": "user", "content": "ciao"})
    run_turn(state, _fake_client({}), [EchoTool()])
    riga = [r for r in capsys.readouterr().out.splitlines() if r.startswith("[")][-1]
    assert "tok in" in riga and "tot]" in riga


def test_guard_rail_segue_max_steps(state: SessionState, capsys) -> None:
    """Il limite del turno e' quello della sessione, non piu' la costante di config."""
    state.max_steps = 2
    state.messages.append({"role": "user", "content": "ciao"})
    # Un modello che chiama sempre lo strumento: il turno finisce solo per guard rail.
    call = {"id": "c1", "type": "function", "function": {"name": "echo", "arguments": '{"message": "x"}'}}
    chunk = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                index=0,
                id=call["id"],
                function=SimpleNamespace(name="echo", arguments='{"message": "x"}'),
            )],
        ))],
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_k: [chunk])))
    run_turn(state, client, [EchoTool()])
    out = capsys.readouterr().out
    assert "limite di 2 step" in out
    assert "step 2/2" in out


def test_conferma_distruttiva_negata_chiude_il_turno(state: SessionState, capsys) -> None:
    """Il turno si ferma invece di riconsegnare l'errore al modello, che proverebbe altre strade."""
    state.messages.append({"role": "user", "content": "ciao"})
    call = {"id": "c1", "type": "function", "function": {"name": "echo", "arguments": '{"message": "x"}'}}
    chunk = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                index=0, id=call["id"], function=SimpleNamespace(name="echo", arguments='{"message": "x"}')
            )],
        ))],
    )
    chiamate: list[int] = []

    def create(**_k: object) -> list:
        chiamate.append(1)
        # La conferma viene negata durante il primo giro di strumenti
        state.abort_reason = "Eseguire rm -rf?"
        return [chunk]

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    run_turn(state, client, [EchoTool()])
    assert len(chiamate) == 1, "il loop non deve chiedere un altro giro al modello"
    assert "azione distruttiva non autorizzata" in capsys.readouterr().out
