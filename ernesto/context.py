"""Contesto del modello: file di istruzioni (soul.md / identity.md / credentials.md) e
indice delle memorie.

Tutti i file letti all'avvio stanno nella sottocartella `context/`, cercata prima nella
cartella di lavoro e poi in ~/.config/ernesto/: la struttura e' la stessa nei due posti.
Le memorie stanno tutte in `memories/` della cartella di lavoro (memory.md persistente e
memory-<ts>.md di sessione) e NON vengono caricate nel prompt: entra l'indice, il
contenuto si legge con read_file quando il modello decide che serve.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .config import CONTEXT_DIR, MEMORY_DIR, MEMORY_FILE, MEMORY_INDEX_LIMIT, config_dir
from .skills import active_skill_parts, discover_skills, skills_index

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
# Blocco di un identity.md che riguarda solo il progetto in cui si trova (vedi
# project_only_section e install-context.py, che usa gli stessi marcatori).
_ONLY_PROJECT_RE = re.compile(
    r"<!-- solo-progetto: inizio.*?-->(.*?)<!-- solo-progetto: fine -->",
    re.DOTALL,
)


@dataclass
class ContextFile:
    """Un file di contesto: nome, percorso trovato, contenuto e provenienza."""

    name: str
    path: Path | None = None
    content: str | None = None
    origin: str = "assente"  # "workdir" | "config" | "assente" | "duplicato"


@dataclass
class Context:
    """I file di contesto caricati all'avvio."""

    workdir: Path
    # Per ogni file di contesto ci sono due posizioni e si SOMMANO sempre: prima il file di
    # ~/.config/ernesto/context/ (valido ovunque), poi quello del progetto, che specializza.
    # Una regola sola per tutti e tre, altrimenti non si sa mai quali istruzioni sono attive.
    soul: ContextFile = field(default_factory=lambda: ContextFile("soul.md"))
    soul_base: ContextFile = field(default_factory=lambda: ContextFile("soul.md"))
    identity: ContextFile = field(default_factory=lambda: ContextFile("identity.md"))
    identity_base: ContextFile = field(default_factory=lambda: ContextFile("identity.md"))
    credentials: ContextFile = field(default_factory=lambda: ContextFile("credentials.md"))
    credentials_base: ContextFile = field(default_factory=lambda: ContextFile("credentials.md"))
    soul_mode: str = "append"  # "append" | "replace"
    # Le memorie non sono file di contesto caricati: nel prompt entra solo il loro indice.
    memory_index: str = ""
    session_memory: str | None = None  # es. "memories/memory-20260917_094311.md"


def _read_file(name: str, base: Path, origin: str) -> ContextFile:
    """Legge un file da `base/context/` (assente o illeggibile = contenuto vuoto)."""
    candidate = base / CONTEXT_DIR / name
    if candidate.is_file():
        try:
            return ContextFile(name, candidate, candidate.read_text(encoding="utf-8"), origin)
        except OSError:
            pass
    return ContextFile(name)


def _load_pair(name: str, workdir: Path) -> tuple[ContextFile, ContextFile]:
    """Carica un file di contesto dalle due posizioni: (globale, progetto).

    Le due parti si sommano. Due casi particolari, gia' necessari per identity.md e ora
    validi per tutti i file:
    - workdir e cartella globale coincidono, o i due file hanno lo stesso contenuto: si
      conta una copia sola;
    - il file di progetto e' la sorgente stessa del globale (contiene i marcatori
      `solo-progetto`): dal locale si prende solo quel blocco, altrimenti il generale
      entrerebbe due volte nel prompt.
    """
    base = _read_file(name, config_dir(), "config")
    progetto = _read_file(name, workdir, "workdir")
    if progetto.path is not None and progetto.path == base.path:
        return ContextFile(name, base.path, None, "duplicato"), progetto
    if base.content is not None and base.content == progetto.content:
        # Stesso contenuto nelle due posizioni (tipico del repo che e' anche la sorgente
        # del globale): si tiene una copia sola, altrimenti il prompt la ripete. Il percorso
        # resta, con origine "duplicato": in /context files "identico al globale" e'
        # un'informazione diversa da "non trovato".
        return base, ContextFile(name, progetto.path, None, "duplicato")
    if base.content and progetto.content:
        solo_progetto = project_only_section(progetto.content)
        if solo_progetto is not None:
            progetto.content = solo_progetto
    return base, progetto


def project_only_section(content: str) -> str | None:
    """Il blocco `solo-progetto` di un identity.md, o None se non c'e'.

    Serve al repository di ernesto, dove lo stesso file e' sia la sorgente delle istruzioni
    globali (install-context.py le copia senza questo blocco) sia il contesto del progetto:
    senza questa estrazione le regole generali entrerebbero due volte nel prompt.
    """
    match = _ONLY_PROJECT_RE.search(content)
    return match.group(1).strip() if match else None


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

    context/soul.md, context/identity.md e context/credentials.md: prima nella cartella di
    lavoro, poi in ~/.config/ernesto/.
    Le memorie non vengono caricate: entra nel prompt solo il loro indice.
    """
    ctx = Context(workdir=workdir)
    ctx.soul_base, ctx.soul = _load_pair("soul.md", workdir)
    ctx.identity_base, ctx.identity = _load_pair("identity.md", workdir)
    ctx.credentials_base, ctx.credentials = _load_pair("credentials.md", workdir)
    ctx.session_memory = session_memory
    ctx.memory_index = memory_index(workdir, session_memory)
    # Il frontmatter `mode: replace` vale se sta in una qualsiasi delle due posizioni.
    for soul in (ctx.soul_base, ctx.soul):
        if soul.content is not None:
            soul.content, mode = parse_soul(soul.content)
            if mode == "replace":
                ctx.soul_mode = "replace"
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
    """Le memorie in memories/: prima la persistente, poi quelle di sessione piu' recenti."""
    files: list[Path] = []
    memories_dir = workdir / MEMORY_DIR
    if not memories_dir.is_dir():
        return files
    persistent = memories_dir / MEMORY_FILE
    if persistent.is_file():
        files.append(persistent)
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
        f"- `{MEMORY_DIR}/{MEMORY_FILE}`: memoria persistente del progetto (fatti durevoli, "
        "preferenze, decisioni). Aggiornala con `edit_file` quando emerge qualcosa che varra' "
        "anche nelle sessioni future.",
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


def context_files(ctx: Context) -> list[tuple[str, ContextFile]]:
    """I file di contesto con la loro posizione effettiva, per /context.

    Un percorso assente e' informazione utile quanto uno presente: dice che quel pezzo di
    contesto non c'e'.
    """
    return [
        ("soul.md (base)", ctx.soul_base),
        ("soul.md (progetto)", ctx.soul),
        ("identity.md (base)", ctx.identity_base),
        ("identity.md (progetto)", ctx.identity),
        ("credentials.md (base)", ctx.credentials_base),
        ("credentials.md (progetto)", ctx.credentials),
    ]


def summary_line(ctx: Context) -> str:
    """Riga di riepilogo, es. `Contesto: soul.md 1 · identity.md 2 · credentials.md 1 · memorie: 2`."""

    def mark(base: ContextFile, progetto: ContextFile) -> str:
        quanti = sum(1 for cf in (base, progetto) if cf.content)
        return f"{base.name} {quanti if quanti else '✗'}"

    return (
        f"Contesto: {mark(ctx.soul_base, ctx.soul)} · {mark(ctx.identity_base, ctx.identity)} · "
        f"{mark(ctx.credentials_base, ctx.credentials)} · memorie: {len(memory_files(ctx.workdir))}"
    )


def system_prompt_parts(
    ctx: Context, json_mode: bool = False, loaded_skills: list[str] | None = None
) -> list[tuple[str, str]]:
    """Le parti del system prompt con etichetta di provenienza (per /context)."""
    attive = loaded_skills or []
    parts: list[tuple[str, str]] = []
    for cf, etichetta in ((ctx.soul_base, "soul.md (base)"), (ctx.soul, "soul.md (progetto)")):
        if cf.content:
            parts.append((etichetta, cf.content))
    # Con `mode: replace` in una qualsiasi delle due posizioni il prompt di default sparisce
    if ctx.soul_mode != "replace":
        parts.append(("prompt di default", f"{BASE_SYSTEM_PROMPT}\n\n{AGENT_SYSTEM_PROMPT}"))
    if ctx.identity_base.content:
        parts.append(("identity.md (base)",
                      f"## Istruzioni operative di base\n\n{ctx.identity_base.content}"))
    if ctx.identity.content:
        parts.append(("identity.md (progetto)",
                      f"## Istruzioni operative del progetto\n\n{ctx.identity.content}"))
    if ctx.memory_index:
        parts.append(("indice memorie", ctx.memory_index))
    disponibili = discover_skills(ctx.workdir)
    indice = skills_index(disponibili, attive)
    if indice:
        parts.append(("indice skill", indice))
    parts.extend(active_skill_parts(ctx.workdir, attive))
    for cf, etichetta in ((ctx.credentials_base, "credentials.md (base)"),
                          (ctx.credentials, "credentials.md (progetto)")):
        if cf.content:
            parts.append((etichetta, f"## Credenziali\n\n{cf.content}"))
    if json_mode:
        parts.append(("JSON mode", JSON_MODE_SUFFIX.strip()))
    return parts


def compose_system_prompt(
    ctx: Context, json_mode: bool = False, loaded_skills: list[str] | None = None
) -> str:
    """Compone il system prompt completo dalle parti di contesto."""
    return "\n\n".join(text for _, text in system_prompt_parts(ctx, json_mode, loaded_skills))


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
