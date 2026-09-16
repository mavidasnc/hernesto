"""Test per il loop agentico: parsing argomenti e gestione tool call."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

from ernesto.agent import run_tool_call, run_turn
from ernesto.models import ModelConfig
from ernesto.tools import Tool


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
        record_usage=lambda *a: None,
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
