"""Strumento di esecuzione comandi con denylist, timeout e troncamento dell'output."""

from __future__ import annotations

import os
import re
import signal
import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from ..config import STDERR_OUTPUT_LIMIT, TOOL_OUTPUT_LIMIT, load_deny_patterns
from . import LEVEL_DESTRUCTIVE, LEVEL_WARNING, ConfirmFn, Tool

if TYPE_CHECKING:
    from ..session import SessionState


# Frammenti che indicano un'uscita dalla cartella di lavoro: path assoluti stile Windows
# (C:\... o C:/...), path assoluti POSIX di sistema, e risalite con "..".
_ESCAPE_PATTERNS = [
    re.compile(r"\b[A-Za-z]:[\\/][^\s\"']*"),
    re.compile(r"(?<![\w./])/(?:etc|usr|bin|var|root|home|tmp|opt|Users)(?:/[^\s\"']*)?"),
    re.compile(r"\.\.[\\/]"),
]


def normalize_command(command: str) -> str:
    """Forma normalizzata per il confronto con la denylist: minuscole, spazi collassati."""
    return re.sub(r"\s+", " ", command.strip().lower())


def find_deny_match(command: str, patterns: list[str]) -> str | None:
    """Restituisce il primo pattern della denylist che matcha il comando, o None.

    Il confronto avviene sulla forma normalizzata e senza distinzione di maiuscole, cosi'
    "RM  -RF" e "rm -r -f" non scivolano via per una differenza di forma.
    """
    normalized = normalize_command(command)
    for pattern in patterns:
        try:
            if re.search(pattern, normalized, re.IGNORECASE):
                return pattern
        except re.error:
            continue  # pattern malformato in config.yaml: ignorato
    return None


def find_escaping_path(command: str) -> str | None:
    """Primo frammento del comando che sembra uscire dalla cartella di lavoro, o None.

    La sandbox vale per gli strumenti filesystem, non per run_command, che esegue una
    shell arbitraria: questa e' una guardia dichiaratamente imperfetta (si aggira in mille
    modi e ha falsi positivi su comandi legittimi), quindi NON blocca, chiede conferma.
    """
    for pattern in _ESCAPE_PATTERNS:
        match = pattern.search(command)
        if match:
            return match.group(0)
    return None


def _truncate(text: str, limit: int) -> str:
    """Tronca a `limit` caratteri aggiungendo la nota di troncamento."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[troncato a {limit} caratteri]"


def _format_output(returncode: int, stdout: str, stderr: str) -> str:
    """Compone il risultato: stdout e stderr troncati separatamente.

    Con stderr vuoto il formato resta `exit N\\n<stdout>` come prima; quando ci sono
    entrambi gli stream vengono etichettati, cosi' il modello distingue i risultati dal
    rumore (warning di npm o pip) invece di trovarseli mescolati.
    """
    stdout = _truncate(stdout, TOOL_OUTPUT_LIMIT)
    stderr = _truncate(stderr, STDERR_OUTPUT_LIMIT)
    if not stderr.strip():
        return f"exit {returncode}\n{stdout}"
    if not stdout.strip():
        return f"exit {returncode}\n--- stderr ---\n{stderr}"
    return f"exit {returncode}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"


def _kill_tree(proc: subprocess.Popen) -> None:
    """Termina il processo e tutta la sua discendenza (best effort, mai eccezioni)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


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
                level=LEVEL_DESTRUCTIVE,
            )
            if not ok:
                return "ERRORE: comando rifiutato dall'utente (denylist di sicurezza)"
        escaping = find_escaping_path(command)
        if escaping is not None and not self._state.yolo:
            ok = self._confirm(
                f"Il comando cita un percorso fuori dalla cartella di lavoro ({escaping!r}). Eseguire comunque?",
                preview=command,
                level=LEVEL_WARNING,
            )
            if not ok:
                return (
                    "ERRORE: comando rifiutato dall'utente (percorso fuori dalla cartella di lavoro). "
                    f"Lavora con percorsi relativi dentro {self._state.workdir}."
                )
        # Popen (invece di subprocess.run) per poter uccidere l'albero dei processi
        # su timeout e su Ctrl+C: il gruppo di processi separato evita che il segnale
        # arrivi direttamente al figlio bypassando la nostra gestione.
        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=str(self._state.workdir),
                stdin=subprocess.DEVNULL,  # un comando interattivo fallisce subito invece di restare appeso
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # encoding esplicito: con il default (codifica locale, cp1252 su Windows) un
                # byte non mappato solleva UnicodeDecodeError DENTRO il thread lettore di
                # communicate(), che non risale al chiamante: l'output spariva lasciando un
                # ingannevole "exit 0" che il modello interpretava come pagina vuota.
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
        except OSError as exc:
            return f"ERRORE: {exc}"
        try:
            stdout, stderr = proc.communicate(timeout=int(timeout))
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return f"ERRORE: timeout dopo {timeout}s"
        except KeyboardInterrupt:
            _kill_tree(proc)
            raise  # risale fino a run_turn, che annulla il turno
        return _format_output(proc.returncode, stdout or "", stderr or "")
