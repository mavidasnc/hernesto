"""Strumenti filesystem con sandbox obbligatoria sulla cartella di lavoro."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..config import MAX_LIST_ENTRIES
from . import Tool

if TYPE_CHECKING:
    from ..session import SessionState

SANDBOX_ERROR = "ERRORE: path fuori dalla sandbox"


def resolve_in_sandbox(workdir: Path, path: str) -> Path | None:
    """Risolve `path` dentro la workdir; None se esce dalla sandbox (inclusi symlink)."""
    base = os.path.realpath(str(workdir))
    candidate = os.path.realpath(os.path.join(base, path))
    if candidate == base or candidate.startswith(base + os.sep):
        return Path(candidate)
    return None


class ListFilesTool(Tool):
    """Elenca file e cartelle con dimensione dentro la cartella di lavoro."""

    name = "list_files"
    description = "Elenca file e cartelle con dimensione dentro la cartella di lavoro."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Percorso relativo alla cartella di lavoro (default: .)"},
            "recursive": {"type": "boolean", "description": "Se true, elenca ricorsivamente", "default": False},
        },
    }

    def __init__(self, state: SessionState) -> None:
        self._state = state

    def run(self, path: str = ".", recursive: bool = False, **_: Any) -> str:
        target = resolve_in_sandbox(self._state.workdir, path)
        if target is None:
            return SANDBOX_ERROR
        try:
            if not target.exists():
                return f"ERRORE: percorso inesistente: {path}"
            if target.is_file():
                return f"{target.stat().st_size:>10}  {path}"
            entries = sorted(target.rglob("*") if recursive else target.iterdir())
            lines = []
            for entry in entries[:MAX_LIST_ENTRIES]:
                try:
                    rel: Any = entry.relative_to(self._state.workdir)
                except ValueError:
                    rel = entry
                if entry.is_dir():
                    lines.append(f"{'<dir>':>10}  {rel}/")
                else:
                    lines.append(f"{entry.stat().st_size:>10}  {rel}")
            note = ""
            if len(entries) > MAX_LIST_ENTRIES:
                note = f"\n…[elenco troncato a {MAX_LIST_ENTRIES} voci]"
            return ("\n".join(lines) + note) if lines else "(cartella vuota)"
        except OSError as exc:
            return f"ERRORE: {exc}"


class ReadFileTool(Tool):
    """Legge un file di testo dentro la cartella di lavoro (paginazione per righe)."""

    name = "read_file"
    description = "Legge il contenuto testuale di un file dentro la cartella di lavoro."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Percorso relativo alla cartella di lavoro"},
            "offset": {"type": "integer", "description": "Riga da cui partire (0-based)", "default": 0},
            "limit": {"type": "integer", "description": "Numero massimo di righe", "default": 500},
        },
        "required": ["path"],
    }

    def __init__(self, state: SessionState) -> None:
        self._state = state

    def run(self, path: str, offset: int = 0, limit: int = 500, **_: Any) -> str:
        target = resolve_in_sandbox(self._state.workdir, path)
        if target is None:
            return SANDBOX_ERROR
        try:
            raw = target.read_bytes()
        except FileNotFoundError:
            return f"ERRORE: file non trovato: {path}"
        except OSError as exc:
            return f"ERRORE: {exc}"
        if b"\x00" in raw[:8192]:
            return "ERRORE: file binario: lettura rifiutata"
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[int(offset): int(offset) + int(limit)]
        if not selected:
            return "(file vuoto o oltre l'offset)"
        note = ""
        if int(offset) + len(selected) < len(lines):
            note = f"\n…[mostrate righe {offset}-{int(offset) + len(selected)} di {len(lines)}]"
        return "\n".join(selected) + note


class WriteFileTool(Tool):
    """Crea o sostituisce un file dentro la cartella di lavoro."""

    name = "write_file"
    description = "Crea o sostituisce un file dentro la cartella di lavoro (crea le directory intermedie)."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Percorso relativo alla cartella di lavoro"},
            "content": {"type": "string", "description": "Contenuto completo del file"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, state: SessionState) -> None:
        self._state = state

    def run(self, path: str, content: str, **_: Any) -> str:
        target = resolve_in_sandbox(self._state.workdir, path)
        if target is None:
            return SANDBOX_ERROR
        if self._state.dry_run:
            return f"DRY-RUN: write_file simulato su {path} ({len(content)} caratteri)"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"ERRORE: {exc}"
        return f"{len(content)} caratteri scritti in {path}"


class EditFileTool(Tool):
    """Sostituzione esatta di una stringa in un file (edit chirurgica)."""

    name = "edit_file"
    description = (
        "Sostituisce una stringa esatta in un file dentro la cartella di lavoro. "
        "Errore se old_string non e' trovata o non e' univoca (a meno di replace_all)."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Percorso relativo alla cartella di lavoro"},
            "old_string": {"type": "string", "description": "Stringa esatta da sostituire"},
            "new_string": {"type": "string", "description": "Stringa sostitutiva"},
            "replace_all": {"type": "boolean", "description": "Sostituisci tutte le occorrenze", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    }

    def __init__(self, state: SessionState) -> None:
        self._state = state

    def run(self, path: str, old_string: str, new_string: str, replace_all: bool = False, **_: Any) -> str:
        target = resolve_in_sandbox(self._state.workdir, path)
        if target is None:
            return SANDBOX_ERROR
        try:
            text = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"ERRORE: file non trovato: {path}"
        except OSError as exc:
            return f"ERRORE: {exc}"
        occurrences = text.count(old_string)
        if occurrences == 0:
            return f"ERRORE: old_string non trovata in {path}"
        if occurrences > 1 and not replace_all:
            return f"ERRORE: old_string non univoca in {path} ({occurrences} occorrenze): usa replace_all"
        if self._state.dry_run:
            return f"DRY-RUN: edit_file simulato su {path} ({occurrences if replace_all else 1} sostituzioni)"
        new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
        try:
            target.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return f"ERRORE: {exc}"
        return f"edit_file su {path}: {occurrences if replace_all else 1} sostituzioni"
