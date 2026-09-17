"""Caricamento dei file di contesto (soul.md / agent.md / memory.md / credentials.md).

Per ciascun file: cerca prima nella cartella di lavoro, poi in ~/.config/ernesto/.
memory.md fa eccezione ed e' cercata solo nella workdir: e' la memoria di lavoro del
singolo progetto, scritta dall'agente stesso, e non deve rientrare altrove.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .config import MEMORY_LIMIT, config_dir

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
    "Mantieni `memory.md` nella cartella di lavoro con i fatti durevoli e le decisioni prese "
    "(non il trascritto della conversazione): aggiornalo con `edit_file` quando emerge qualcosa "
    "che servira' anche nelle sessioni future, e tienilo sotto le 4000 battute potando cio' che non serve piu'."
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
    memory: ContextFile = field(default_factory=lambda: ContextFile("memory.md"))
    soul_mode: str = "append"  # "append" | "replace"


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


def load_context(workdir: Path) -> Context:
    """Carica soul.md, agent.md, credentials.md (workdir, poi ~/.config/) e memory.md."""
    ctx = Context(workdir=workdir)
    ctx.soul = _find_file("soul.md", workdir)
    ctx.agent = _find_file("agent.md", workdir)
    ctx.credentials = _find_file("credentials.md", workdir)
    ctx.memory = _find_file("memory.md", workdir, workdir_only=True)
    if ctx.soul.content is not None:
        ctx.soul.content, ctx.soul_mode = parse_soul(ctx.soul.content)
    return ctx


def _capped_memory(content: str) -> str:
    """Tronca la memoria al tetto: il system prompt viaggia in ogni richiesta di ogni step."""
    if len(content) <= MEMORY_LIMIT:
        return content
    return content[:MEMORY_LIMIT] + f"\n…[memoria troncata a {MEMORY_LIMIT} caratteri: potala con edit_file]"


def reload_memory(ctx: Context) -> bool:
    """Ricarica memory.md dalla workdir. True se il contenuto e' cambiato.

    Serve perche' l'agente scrive memory.md durante la sessione: senza rilettura il
    system prompt resterebbe quello composto all'avvio fino al prossimo /clear.
    """
    before = ctx.memory.content
    ctx.memory = _find_file("memory.md", ctx.workdir, workdir_only=True)
    return ctx.memory.content != before


def summary_line(ctx: Context) -> str:
    """Riga di riepilogo del contesto, es. `Contesto: soul.md ✓ · agent.md ✓ · credentials.md ✗`."""

    def mark(cf: ContextFile) -> str:
        return f"{cf.name} {'✓' if cf.content is not None else '✗'}"

    return f"Contesto: {mark(ctx.soul)} · {mark(ctx.agent)} · {mark(ctx.credentials)} · {mark(ctx.memory)}"


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
    if ctx.memory.content:
        parts.append((f"memory.md ({ctx.memory.path or ctx.memory.name})",
                      f"## Memoria di lavoro\n\n{_capped_memory(ctx.memory.content)}"))
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
