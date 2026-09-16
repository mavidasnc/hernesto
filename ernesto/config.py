"""Configurazione di ernesto: costanti, parser .env minimale, denylist da config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

MAX_AGENT_STEPS = 30
TOOL_OUTPUT_LIMIT = 8000
LOG_CONTENT_LIMIT = 4000
MAX_LIST_ENTRIES = 500
MCP_TOOL_TIMEOUT = 60

# Pattern pericolosi di default per run_command (regex): richiedono conferma.
DEFAULT_DENY_PATTERNS: list[str] = [
    r"rm\s+-rf",
    r"\bsudo\b",
    r"git\s+push",
    r"git\s+reset\s+--hard",
    r"docker\s+system\s+prune",
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;:",  # fork bomb :(){ :|:& };:
]


def config_dir() -> Path:
    """Cartella di fallback per i file di contesto e di configurazione."""
    return Path.home() / ".config" / "ernesto"


def load_env_file(path: Path) -> None:
    """Parser .env minimale: popola os.environ SOLO per le chiavi non gia' presenti.

    Ignora commenti e righe vuote, divide su `=`, rimuove le virgolette attorno al valore.
    Il file .env e' un fallback: credentials.md resta la fonte dichiarativa delle
    variabili richieste.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_deny_patterns(workdir: Path) -> list[str]:
    """Denylist completa: pattern di default + `safety.deny_patterns` da config.yaml.

    config.yaml viene cercato nella workdir poi in ~/.config/ernesto/. Richiede PyYAML:
    se non e' installato o il file e' malformato, viene ignorato senza errore.
    """
    patterns = list(DEFAULT_DENY_PATTERNS)
    cfg = workdir / "config.yaml"
    if not cfg.is_file():
        cfg = config_dir() / "config.yaml"
    if not cfg.is_file():
        return patterns
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return patterns
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        extra = (data.get("safety") or {}).get("deny_patterns") or []
        patterns.extend(str(p) for p in extra)
    except Exception:
        pass
    return patterns
