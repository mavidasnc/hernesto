"""Test delle skill: scoperta, precedenza, indice e caricamento nel system prompt."""

from __future__ import annotations

from pathlib import Path

import pytest

from ernesto.config import SKILLS_DIR
from ernesto.context import compose_system_prompt, load_context
from ernesto.skills import discover_skills, find_skill, skill_body, skills_index

SKILL_WP = """---
name: wordpress
description: Convenzioni e sicurezza WordPress
---

Usa sempre wpdb::prepare.
"""


def _scrivi_skill(base: Path, cartella: str, contenuto: str) -> Path:
    """Crea skills/<cartella>/SKILL.md sotto una base e restituisce il percorso."""
    d = base / SKILLS_DIR / cartella
    d.mkdir(parents=True, exist_ok=True)
    file = d / "SKILL.md"
    file.write_text(contenuto, encoding="utf-8")
    return file


def test_scoperta_legge_i_metadati(workdir: Path) -> None:
    """Nome e descrizione arrivano dal frontmatter."""
    _scrivi_skill(workdir, "wordpress", SKILL_WP)
    skills = discover_skills(workdir)
    assert [s.name for s in skills] == ["wordpress"]
    assert skills[0].description == "Convenzioni e sicurezza WordPress"
    assert skills[0].origin == "progetto"


def test_skill_senza_frontmatter_ignorata(workdir: Path) -> None:
    """Un file scritto male viene saltato, non fa fallire l'avvio."""
    _scrivi_skill(workdir, "rotta", "# Nessun frontmatter qui\n")
    _scrivi_skill(workdir, "senza-descrizione", "---\nname: x\n---\ncorpo\n")
    assert discover_skills(workdir) == []


def test_cartella_senza_skill_md_ignorata(workdir: Path) -> None:
    """Una cartella qualsiasi dentro skills/ non e' una skill."""
    (workdir / SKILLS_DIR / "appunti").mkdir(parents=True)
    (workdir / SKILLS_DIR / "appunti" / "note.txt").write_text("x", encoding="utf-8")
    assert discover_skills(workdir) == []


def test_progetto_vince_su_globale(workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A parita' di nome, la skill del progetto specializza quella globale."""
    fake_config = tmp_path / "config-home"
    _scrivi_skill(fake_config, "wordpress", SKILL_WP.replace("Usa sempre", "Versione globale:"))
    _scrivi_skill(workdir, "wordpress", SKILL_WP)
    monkeypatch.setattr("ernesto.skills.config_dir", lambda: fake_config)
    skills = discover_skills(workdir)
    assert len(skills) == 1
    assert skills[0].origin == "progetto"
    assert "Usa sempre wpdb::prepare." in skill_body(skills[0])


def test_skill_globale_visibile_ovunque(workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Una skill in ~/.config/ernesto/skills vale in qualunque cartella di lavoro."""
    fake_config = tmp_path / "config-home"
    _scrivi_skill(fake_config, "wordpress", SKILL_WP)
    monkeypatch.setattr("ernesto.skills.config_dir", lambda: fake_config)
    skills = discover_skills(workdir)
    assert [s.origin for s in skills] == ["globale"]


def test_indice_senza_corpi(workdir: Path) -> None:
    """Nel prompt entra l'elenco, non il contenuto delle skill."""
    _scrivi_skill(workdir, "wordpress", SKILL_WP)
    prompt = compose_system_prompt(load_context(workdir))
    assert "wordpress" in prompt
    assert "Convenzioni e sicurezza WordPress" in prompt
    assert "wpdb::prepare" not in prompt
    assert "/skill" in prompt  # il modello sa come proporne l'attivazione


def test_skill_attiva_entra_nel_prompt(workdir: Path) -> None:
    """Caricata, la skill porta il suo corpo nel system prompt."""
    _scrivi_skill(workdir, "wordpress", SKILL_WP)
    ctx = load_context(workdir)
    assert "wpdb::prepare" in compose_system_prompt(ctx, loaded_skills=["wordpress"])
    assert "[attiva]" in skills_index(discover_skills(workdir), ["wordpress"])
    # e scaricandola sparisce
    assert "wpdb::prepare" not in compose_system_prompt(ctx, loaded_skills=[])


def test_skill_attiva_inesistente_non_rompe(workdir: Path) -> None:
    """Un nome sbagliato fra le attive viene semplicemente ignorato."""
    assert isinstance(compose_system_prompt(load_context(workdir), loaded_skills=["fantasma"]), str)


def test_find_skill_ignora_le_maiuscole(workdir: Path) -> None:
    """`/skill WordPress` trova `wordpress`."""
    _scrivi_skill(workdir, "wordpress", SKILL_WP)
    assert find_skill(workdir, "WordPress") is not None
    assert find_skill(workdir, "inesistente") is None


def test_nessuna_skill_nessun_indice(workdir: Path) -> None:
    """Senza skill il prompt non contiene la sezione: chi non le usa non paga token."""
    assert "Skill disponibili" not in compose_system_prompt(load_context(workdir))
