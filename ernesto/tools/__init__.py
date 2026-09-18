"""Registry degli strumenti di ernesto.

Ogni strumento e' una classe con `name`, `description`, `parameters` (JSON schema)
e un metodo `run(**kwargs) -> str` che NON lancia mai eccezioni verso il modello:
converte sempre gli errori in stringhe "ERRORE: ...".
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ernesto.session import SessionState

# Livelli di gravita' della conferma, dal piu' grave: cambiano etichetta e colore mostrati
# all'utente, cosi' un rm -rf non arriva con lo stesso aspetto di una email.
LEVEL_DESTRUCTIVE = "distruttivo"  # perdita di dati o azioni irreversibili sulla macchina
LEVEL_EXTERNAL = "esterno"         # qualcosa esce dalla macchina (email, push)
LEVEL_WARNING = "attenzione"       # legittimo ma fuori dai confini attesi

# Callback di conferma iniettato dal runner: (messaggio, anteprima, livello) -> bool
ConfirmFn = Callable[..., bool]


class Tool:
    """Classe base degli strumenti."""

    name: str = ""
    description: str = ""
    parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def run(self, **kwargs: Any) -> str:
        """Esegue lo strumento. Non deve mai lanciare eccezioni."""
        raise NotImplementedError


def tool_schemas(tools: list[Tool]) -> list[dict[str, Any]]:
    """Genera gli schema OpenAI `{"type": "function", "function": {...}}` per l'API."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def build_native_tools(state: SessionState, confirm_fn: ConfirmFn) -> list[Tool]:
    """Costruisce la lista degli strumenti nativi attivi per la sessione."""
    from .filesystem import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
    from .imap import ImapDeleteTool, ImapFoldersTool, ImapListTool, ImapMoveTool, ImapReadTool
    from .mail import SendEmailTool
    from .shell import RunCommandTool
    from .web import BraveSearchTool, FetchUrlTool

    return [
        ListFilesTool(state),
        ReadFileTool(state),
        WriteFileTool(state),
        EditFileTool(state),
        RunCommandTool(state, confirm_fn),
        BraveSearchTool(),
        FetchUrlTool(),
        SendEmailTool(state, confirm_fn),
        ImapFoldersTool(state),
        ImapListTool(state),
        ImapReadTool(state),
        ImapMoveTool(state, confirm_fn),
        ImapDeleteTool(state, confirm_fn),
    ]
