"""Configurazione di ernesto: costanti, parser .env minimale, denylist da config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

MAX_AGENT_STEPS = 30
TOOL_OUTPUT_LIMIT = 8000
STDERR_OUTPUT_LIMIT = 2000  # stderr ha un tetto piu' basso: e' rumore piu' spesso che segnale
LOG_CONTENT_LIMIT = 4000
MAX_LIST_ENTRIES = 500
MCP_TOOL_TIMEOUT = 60

# Compattazione della storia: sopra la soglia i risultati degli strumenti piu' vecchi
# diventano un riassunto deterministico. La soglia e' in token stimati e non in numero di
# step perche' il costo dipende dai token: venti list_files sono innocui, tre read_file da
# 8000 caratteri no.
COMPACT_THRESHOLD_TOKENS = 30_000
COMPACT_KEEP_RECENT = 3     # giri assistant+tool mantenuti integrali
COMPACT_MIN_CHARS = 500     # sotto questa soglia il riassunto non risparmierebbe nulla
COMPACT_HEAD_CHARS = 300    # testa del contenuto conservata nel riassunto
# Modello usato per il riassunto LLM della compattazione: deve essere economico, perche'
# riassumere il payload piu' grande della sessione con un modello caro vanifica il risparmio.
COMPACT_SUMMARY_MODEL = "google/gemini-2.5-flash"
COMPACT_SUMMARY_MAX_CHARS = 6000  # quanto contenuto si manda al riassuntore

# Voci massime nell'indice delle memorie dentro il system prompt: l'indice e' piccolo per
# costruzione (nome, data, prima riga), il contenuto si legge con read_file quando serve.
MEMORY_INDEX_LIMIT = 10
MEMORY_DIR = "memories"
MEMORY_FILE = "memory.md"  # la memoria persistente, accanto a quelle di sessione

# Tutti i file letti all'avvio stanno in questa sottocartella, sia nella cartella di lavoro
# sia in ~/.config/ernesto/: una sola regola da ricordare, nessun file di configurazione
# sparso nella radice del progetto (l'unica eccezione e' .env).
CONTEXT_DIR = "context"

# Pattern pericolosi di default per run_command (regex): richiedono conferma.
# Il comando viene normalizzato prima del confronto (minuscole, spazi collassati) e il match
# e' case-insensitive, cosi' "RM  -RF" e "rm -r -f" non scivolano via.
# Resta comunque una difesa contro la DISATTENZIONE: chi voglia eluderla ci riesce (uno
# script, un alias, un eseguibile intermedio). La difesa vera sarebbe l'isolamento.
DEFAULT_DENY_PATTERNS: list[str] = [
    # rm distruttivo: flag uniti (-rf, -fr), lunghi (--recursive --force) o separati
    r"\brm\b[^|;&]*\s-{1,2}(?:[a-z]*r[a-z]*f|[a-z]*f[a-z]*r|recursive|force)\b",
    r"\brm\b[^|;&]*\s-{1,2}(?:r|recursive)\b[^|;&]*\s-{1,2}(?:f|force)\b",
    r"\brm\b[^|;&]*\s-{1,2}(?:f|force)\b[^|;&]*\s-{1,2}(?:r|recursive)\b",
    r"\bsudo\b",
    r"\bgit\b[^|;&]*\bpush\b",  # copre anche "git -C . push"
    r"\bgit\b[^|;&]*\breset\b[^|;&]*--hard\b",
    r"\bdocker\b[^|;&]*\bsystem\b[^|;&]*\bprune\b",
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


_user_config_cache: dict[str, Any] = {}


def load_user_config(workdir: Path, refresh: bool = False) -> dict[str, Any]:
    """Legge context/config.yaml (workdir, poi ~/.config/ernesto/) come dizionario.

    Vince il primo file trovato: i due non vengono fusi. Un file assente, PyYAML non
    installato o uno YAML malformato producono un dizionario vuoto, mai un errore: la
    configurazione e' un di piu', non un requisito per avviare ernesto.
    """
    key = str(workdir)
    if not refresh and key in _user_config_cache:
        return _user_config_cache[key]
    data: dict[str, Any] = {}
    cfg = workdir / CONTEXT_DIR / "config.yaml"
    if not cfg.is_file():
        cfg = config_dir() / CONTEXT_DIR / "config.yaml"
    if cfg.is_file():
        try:
            import yaml  # type: ignore[import-untyped]

            loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass  # config.yaml malformato o PyYAML assente: si continua senza
    _user_config_cache[key] = data
    return data


def config_section(workdir: Path, name: str) -> dict[str, Any]:
    """Una sezione di config.yaml come dizionario (vuoto se assente o non valida)."""
    section = load_user_config(workdir).get(name)
    return section if isinstance(section, dict) else {}


def load_deny_patterns(workdir: Path) -> list[str]:
    """Denylist completa: pattern di default piu' `safety.deny_patterns` da config.yaml."""
    patterns = list(DEFAULT_DENY_PATTERNS)
    extra = config_section(workdir, "safety").get("deny_patterns") or []
    if isinstance(extra, list):
        patterns.extend(str(p) for p in extra)
    return patterns
