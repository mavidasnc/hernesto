"""Contesto del modello: file di istruzioni (soul.md / agent.md / credentials.md) e
indice delle memorie.

I file di contesto vengono cercati nella cartella di lavoro e poi in ~/.config/ernesto/.
Le memorie (memory.md persistente e memories/memory-<ts>.md di sessione) sono invece solo
della cartella di lavoro e NON vengono caricate nel prompt: entra l'indice, il contenuto
si legge con read_file quando il modello decide che serve.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .config import MEMORY_DIR, MEMORY_INDEX_LIMIT, config_dir

BASE_SYSTEM_PROMPT = (
    "Sei un assistente utile e conciso. "
    "Rispondi sempre in italiano, a meno che l'utente non ti scriva in un'altra lingua."
)

AGENT_SYSTEM_PROMPT = (
    "Sei un assistente da terminale con accesso a strumenti. "
    "Lavori SOLO nella cartella corrente. "
    "Usa gli strumenti per leggere/scrivere file, eseguire comandi, cercare sul web e inviare email. "
    "Prima di operare su file o eseguire comandi, leggi/verifica quando necessario. "
    "Dopo ogni modifica al codice, verifica con gli strumenti appropriati (es. test o linter) "
    "se l'utente lo chiede o se è evidente che serve. "
    "Non inventare contenuti di file che non hai letto. "
    "Consulta `credentials.md` per sapere quali credenziali sono disponibili e come usarle: "
    "i valori stanno nelle variabili d'ambiente, non stamparli mai. "
    "Riassumi a fine task i file toccati e le azioni eseguite. "
    "Hai due memorie su file, elencate piu' sotto: una persistente per il progetto e una della "
    "sessione corrente. Non sono nel contesto: leggile con `read_file` solo quando ti servono "
    "davvero, e aggiornale mentre lavori tenendole brevi e potate."
)

JSON_MODE_SUFFIX = " Rispondi SEMPRE con JSON valido. Nessun testo al di fuori del JSON."

# Variabili la cui assenza e' fatale all'avvio.
REQUIRED_ENV_VARS = ("OPENROUTER_API_KEY",)

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_ENV_VAR_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")
_FRONTMATTER_MODE_RE = re.compile(r"^mode:\s*(replace|append)\s*$", re.IGNORECASE)


@dataclass
class ContextFile:
    """Un file di contesto: nome, percorso trovato, contenuto e provenienza."""

    name: str
    path: Path | None = None
    content: str | None = None
    origin: str = "assente"  # "workdir" | "config" | "assente"


@dataclass
class Context:
    """I file di contesto caricati all'avvio."""

    workdir: Path
    soul: ContextFile = field(default_factory=lambda: ContextFile("soul.md"))
    agent: ContextFile = field(default_factory=lambda: ContextFile("agent.md"))
    credentials: ContextFile = field(default_factory=lambda: ContextFile("credentials.md"))
    soul_mode: str = "append"  # "append" | "replace"
    # Le memorie non sono file di contesto caricati: nel prompt entra solo il loro indice.
    memory_index: str = ""
    session_memory: str | None = None  # es. "memories/memory-20260917_094311.md"


def _find_file(name: str, workdir: Path, workdir_only: bool = False) -> ContextFile:
    """Cerca un file di contesto nella workdir poi in ~/.config/ernesto/.

    Con workdir_only la ricerca si ferma alla cartella di lavoro: e' il caso di memory.md,
    che e' per progetto e non deve rientrare da ~/.config in ogni altro progetto.
    """
    bases = ((workdir, "workdir"),) if workdir_only else ((workdir, "workdir"), (config_dir(), "config"))
    for base, origin in bases:
        candidate = base / name
        if candidate.is_file():
            try:
                return ContextFile(name, candidate, candidate.read_text(encoding="utf-8"), origin)
            except OSError:
                return ContextFile(name)
    return ContextFile(name)


def parse_soul(content: str) -> tuple[str, str]:
    """Estrae il frontmatter `mode: replace|append` da soul.md.

    Supporta sia un blocco delimitato da `---` sia una riga isolata nelle prime righe.
    Restituisce (contenuto senza frontmatter, mode).
    """
    mode = "append"
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                for header_line in lines[1:i]:
                    m = _FRONTMATTER_MODE_RE.match(header_line.strip())
                    if m:
                        mode = m.group(1).lower()
                return "\n".join(lines[i + 1:]).strip(), mode
        return content, mode  # blocco mai chiuso: ignora il frontmatter
    for line in lines[:5]:
        m = _FRONTMATTER_MODE_RE.match(line.strip())
        if m:
            mode = m.group(1).lower()
            lines = [ln for ln in lines if not _FRONTMATTER_MODE_RE.match(ln.strip())]
            return "\n".join(lines).strip(), mode
    return content, mode


def load_context(workdir: Path, session_memory: str | None = None) -> Context:
    """Carica i file di contesto e costruisce l'indice delle memorie.

    soul.md / agent.md / credentials.md: workdir, poi ~/.config/ernesto/.
    Le memorie non vengono caricate: entra nel prompt solo il loro indice.
    """
    ctx = Context(workdir=workdir)
    ctx.soul = _find_file("soul.md", workdir)
    ctx.agent = _find_file("agent.md", workdir)
    ctx.credentials = _find_file("credentials.md", workdir)
    ctx.session_memory = session_memory
    ctx.memory_index = memory_index(workdir, session_memory)
    if ctx.soul.content is not None:
        ctx.soul.content, ctx.soul_mode = parse_soul(ctx.soul.content)
    return ctx


def _first_line(path: Path, limit: int = 80) -> str:
    """Prima riga non vuota di un file, troncata: serve a dare un'idea del contenuto."""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    return stripped[:limit]
    except OSError:
        pass
    return "(vuota)"


def memory_files(workdir: Path, limit: int = MEMORY_INDEX_LIMIT) -> list[Path]:
    """memory.md piu' le memorie di sessione in memories/, dalla piu' recente."""
    files: list[Path] = []
    persistent = workdir / "memory.md"
    if persistent.is_file():
        files.append(persistent)
    memories_dir = workdir / MEMORY_DIR
    if memories_dir.is_dir():
        sessions = sorted(memories_dir.glob("memory-*.md"), key=lambda p: p.name, reverse=True)
        files.extend(sessions[:limit])
    return files


def memory_index(workdir: Path, session_file: str | None = None) -> str:
    """Indice delle memorie da mettere nel system prompt.

    Solo nomi, dimensioni e prima riga: il contenuto NON entra nel prompt, perche' il
    prompt viaggia in ogni richiesta di ogni step e la maggior parte delle volte la
    memoria non serve. Il modello la legge con read_file quando decide che gli serve.
    """
    righe = [
        "## Memorie disponibili",
        "",
        "Non sono caricate nel contesto: leggile con `read_file` SOLO quando ti servono "
        "per capire il contesto o riprendere un lavoro.",
        "- `memory.md`: memoria persistente del progetto (fatti durevoli, preferenze, decisioni). "
        "Aggiornala con `edit_file` quando emerge qualcosa che varra' anche nelle sessioni future.",
    ]
    if session_file:
        righe.append(
            f"- `{session_file}`: memoria di QUESTA sessione (stato del lavoro in corso, esiti "
            f"intermedi, cosa resta da fare). Creala con `write_file` e aggiornala mentre lavori."
        )
    trovate = memory_files(workdir)
    if trovate:
        righe.append("")
        righe.append("Gia' presenti nella cartella di lavoro:")
        for path in trovate:
            rel = path.relative_to(workdir).as_posix()
            size = path.stat().st_size if path.is_file() else 0
            righe.append(f"  - `{rel}` ({size} byte) — {_first_line(path)}")
    else:
        righe.append("")
        righe.append("Nessun file di memoria presente al momento.")
    return "\n".join(righe)


def reload_memory(ctx: Context) -> bool:
    """Ricalcola l'indice delle memorie. True se e' cambiato rispetto a prima.

    Serve perche' l'agente crea e aggiorna i file di memoria durante la sessione: senza
    ricalcolo il system prompt resterebbe quello composto all'avvio fino al prossimo /clear.
    """
    before = ctx.memory_index
    ctx.memory_index = memory_index(ctx.workdir, ctx.session_memory)
    return ctx.memory_index != before


def summary_line(ctx: Context) -> str:
    """Riga di riepilogo del contesto, es. `Contesto: soul.md ✓ · agent.md ✓ · credentials.md ✗`."""

    def mark(cf: ContextFile) -> str:
        return f"{cf.name} {'✓' if cf.content is not None else '✗'}"

    memorie = len(memory_files(ctx.workdir))
    return (
        f"Contesto: {mark(ctx.soul)} · {mark(ctx.agent)} · {mark(ctx.credentials)} · "
        f"memorie: {memorie}"
    )


def system_prompt_parts(ctx: Context, json_mode: bool = False) -> list[tuple[str, str]]:
    """Le parti del system prompt con etichetta di provenienza (per /context)."""
    parts: list[tuple[str, str]] = []
    if ctx.soul.content and ctx.soul_mode == "replace":
        origin = ctx.soul.path or ctx.soul.name
        parts.append((f"soul.md (mode: replace, {origin})", ctx.soul.content))
    else:
        if ctx.soul.content:
            parts.append((f"soul.md ({ctx.soul.path or ctx.soul.name})", ctx.soul.content))
        parts.append(("prompt di default", f"{BASE_SYSTEM_PROMPT}\n\n{AGENT_SYSTEM_PROMPT}"))
    if ctx.agent.content:
        parts.append((f"agent.md ({ctx.agent.path or ctx.agent.name})",
                      f"## Istruzioni operative del progetto\n\n{ctx.agent.content}"))
    if ctx.memory_index:
        parts.append(("indice memorie", ctx.memory_index))
    if ctx.credentials.content:
        parts.append((f"credentials.md ({ctx.credentials.path or ctx.credentials.name})",
                      f"## Credenziali del progetto\n\n{ctx.credentials.content}"))
    if json_mode:
        parts.append(("JSON mode", JSON_MODE_SUFFIX.strip()))
    return parts


def compose_system_prompt(ctx: Context, json_mode: bool = False) -> str:
    """Compone il system prompt completo dalle parti di contesto."""
    return "\n\n".join(text for _, text in system_prompt_parts(ctx, json_mode))


def extract_env_vars(credentials_text: str) -> list[str]:
    """Estrae da credentials.md i nomi di variabili d'ambiente (MAIUSCOLO_CON_UNDERSCORE).

    Cerca nei token in inline code (`NOME_VAR`) e nelle intestazioni markdown.
    """
    candidates: list[str] = [m.group(1) for m in _INLINE_CODE_RE.finditer(credentials_text)]
    for line in credentials_text.splitlines():
        heading = _HEADING_RE.match(line.strip())
        if heading:
            candidates.append(heading.group(1))
    found: list[str] = []
    for candidate in candidates:
        for m in _ENV_VAR_RE.finditer(candidate):
            name = m.group(1)
            if name not in found:
                found.append(name)
    return found


@dataclass
class EnvCheck:
    """Esito della verifica delle variabili d'ambiente dichiarate in credentials.md."""

    present: list[str] = field(default_factory=list)
    optional_missing: list[str] = field(default_factory=list)
    fatal_missing: list[str] = field(default_factory=list)


def verify_env_vars(env_vars: list[str], environ: Mapping[str, str] | None = None) -> EnvCheck:
    """Verifica le variabili dichiarate contro l'ambiente.

    Le variabili in REQUIRED_ENV_VARS sono sempre verificate, anche se credentials.md
    non le dichiara (o non esiste): la loro assenza e' fatale.
    """
    env = os.environ if environ is None else environ
    check = EnvCheck()
    names = list(dict.fromkeys([*REQUIRED_ENV_VARS, *env_vars]))
    for name in names:
        if env.get(name):
            check.present.append(name)
        elif name in REQUIRED_ENV_VARS:
            check.fatal_missing.append(name)
        else:
            check.optional_missing.append(name)
    return check
