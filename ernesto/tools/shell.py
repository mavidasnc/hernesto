"""Strumento di esecuzione comandi con denylist, timeout e troncamento dell'output."""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from ..config import TOOL_OUTPUT_LIMIT, load_deny_patterns
from . import ConfirmFn, Tool

if TYPE_CHECKING:
    from ..session import SessionState


def find_deny_match(command: str, patterns: list[str]) -> str | None:
    """Restituisce il primo pattern della denylist che matcha il comando, o None."""
    for pattern in patterns:
        try:
            if re.search(pattern, command):
                return pattern
        except re.error:
            continue  # pattern malformato in config.yaml: ignorato
    return None


class RunCommandTool(Tool):
    """Esegue un comando di shell nella cartella di lavoro."""

    name = "run_command"
    description = (
        "Esegue un comando CLI nella cartella di lavoro (shell di sistema). "
        "Restituisce exit code, stdout e stderr."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando da eseguire"},
            "timeout": {"type": "integer", "description": "Timeout in secondi", "default": 120},
        },
        "required": ["command"],
    }

    def __init__(self, state: SessionState, confirm_fn: ConfirmFn) -> None:
        self._state = state
        self._confirm = confirm_fn
        self._deny_patterns = load_deny_patterns(state.workdir)

    def run(self, command: str, timeout: int = 120, **_: Any) -> str:
        if self._state.dry_run:
            return f"DRY-RUN: comando non eseguito: {command}"
        # Policy denylist (decisione documentata): TUTTI i pattern — quelli di default
        # e quelli aggiunti via config.yaml (safety.deny_patterns) — richiedono conferma
        # interattiva. Con --yolo (o /yolo) la conferma e' saltata; se stdin non e' un
        # TTY il callback di conferma restituisce False e il comando viene rifiutato.
        matched = find_deny_match(command, self._deny_patterns)
        if matched is not None and not self._state.yolo:
            ok = self._confirm(
                f"Il comando matcha un pattern pericoloso ({matched!r}). Eseguire comunque?",
                preview=command,
            )
            if not ok:
                return "ERRORE: comando rifiutato dall'utente (denylist di sicurezza)"
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(self._state.workdir),
                capture_output=True,
                text=True,
                timeout=int(timeout),
            )
        except subprocess.TimeoutExpired:
            return f"ERRORE: timeout dopo {timeout}s"
        except OSError as exc:
            return f"ERRORE: {exc}"
        output = (completed.stdout or "") + (completed.stderr or "")
        note = ""
        if len(output) > TOOL_OUTPUT_LIMIT:
            output = output[:TOOL_OUTPUT_LIMIT]
            note = f"\n…[output troncato a {TOOL_OUTPUT_LIMIT} caratteri]"
        return f"exit {completed.returncode}\n{output}{note}"
