"""Skill caricabili su richiesta.

Una skill e' un corpo di conoscenza specialistica (convenzioni di un linguaggio, regole di
un cliente, un tono di scrittura) che serve solo in alcune sessioni: tenerlo sempre nel
system prompt costerebbe token in ogni richiesta di ogni step, lasciarlo fuori lo
renderebbe inutile. Si carica con `/skill` e resta attivo per la sessione.

Sta in `skills/<nome>/SKILL.md`, con frontmatter `name` e `description`; la cartella
permette di tenere accanto script ed esempi, che il modello legge con read_file quando la
skill glielo dice. Le skill si cercano nella cartella di lavoro e in ~/.config/ernesto/:
a parita' di nome vince quella del progetto.

Differenza dai playbook: un playbook e' una PROCEDURA che il modello consulta da se' quando
riconosce l'attivita'; una skill e' CONOSCENZA che l'utente attiva e che resta nel prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import SKILLS_DIR, config_dir

SKILL_FILE = "SKILL.md"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_FIELD_RE = re.compile(r"^(name|description):\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class Skill:
    """Una skill trovata su disco: metadati sempre, corpo solo quando serve."""

    name: str
    description: str
    path: Path
    origin: str  # "progetto" | "globale"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Separa il frontmatter dal corpo. Senza frontmatter restituisce ({}, testo)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    campi = {k.lower(): v for k, v in _FIELD_RE.findall(match.group(1))}
    return campi, match.group(2)


def _read_skill(cartella: Path, origin: str) -> Skill | None:
    """Legge i metadati di una skill. None se manca SKILL.md o il frontmatter."""
    file = cartella / SKILL_FILE
    if not file.is_file():
        return None
    try:
        campi, _ = parse_frontmatter(file.read_text(encoding="utf-8"))
    except OSError:
        return None
    # Senza descrizione la skill non e' presentabile in un elenco: si ignora invece di
    # mostrarla muta, ma senza far fallire l'avvio per un file scritto male.
    if not campi.get("description"):
        return None
    return Skill(campi.get("name") or cartella.name, campi["description"], file, origin)


def discover_skills(workdir: Path) -> list[Skill]:
    """Skill disponibili, in ordine alfabetico. Legge solo i metadati, mai i corpi.

    Cerca prima in ~/.config/ernesto/skills/ e poi in <workdir>/skills/: a parita' di nome
    vince quella del progetto, cosi' un progetto puo' specializzare una skill generale.
    """
    trovate: dict[str, Skill] = {}
    for base, origin in ((config_dir(), "globale"), (workdir, "progetto")):
        radice = base / SKILLS_DIR
        if not radice.is_dir():
            continue
        for cartella in sorted(radice.iterdir()):
            if not cartella.is_dir():
                continue
            skill = _read_skill(cartella, origin)
            if skill is not None:
                trovate[skill.name] = skill
    return sorted(trovate.values(), key=lambda s: s.name)


def find_skill(workdir: Path, name: str) -> Skill | None:
    """Cerca una skill per nome (confronto senza distinzione di maiuscole)."""
    cercato = name.strip().lower()
    return next((s for s in discover_skills(workdir) if s.name.lower() == cercato), None)


def skill_body(skill: Skill) -> str:
    """Corpo della skill, senza frontmatter. Stringa vuota se il file non e' leggibile."""
    try:
        _, corpo = parse_frontmatter(skill.path.read_text(encoding="utf-8"))
    except OSError:
        return ""
    return corpo.strip()


def skills_index(skills: list[Skill], attive: list[str]) -> str:
    """Elenco delle skill per il system prompt: nomi e descrizioni, mai i corpi."""
    if not skills:
        return ""
    righe = [
        "## Skill disponibili",
        "",
        "Conoscenze specialistiche non caricate nel contesto. Quando una di queste "
        "aiuterebbe il compito in corso, proponi all'utente di attivarla con `/skill <nome>` "
        "invece di procedere a memoria.",
    ]
    for skill in skills:
        stato = " [attiva]" if skill.name in attive else ""
        righe.append(f"- `{skill.name}`{stato}: {skill.description}")
    return "\n".join(righe)


def active_skill_parts(workdir: Path, attive: list[str]) -> list[tuple[str, str]]:
    """Le parti di system prompt delle skill attive, nell'ordine di caricamento."""
    parti: list[tuple[str, str]] = []
    for nome in attive:
        skill = find_skill(workdir, nome)
        if skill is None:
            continue
        corpo = skill_body(skill)
        if corpo:
            parti.append((f"skill: {skill.name}", f"## Skill attiva: {skill.name}\n\n{corpo}"))
    return parti
