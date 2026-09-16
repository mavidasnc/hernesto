"""Test per il loop agentico: parsing argomenti e gestione tool call."""

from __future__ import annotations

from typing import ClassVar

from ernesto.agent import run_tool_call
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
