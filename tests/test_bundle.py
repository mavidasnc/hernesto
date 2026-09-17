"""Test per build_bundle: percorso di ricerca del runtime ed esclusioni dalla copia."""

from __future__ import annotations

from build_bundle import EXCLUDED, SOURCES, ignored, patched_pth

# Il file `._pth` come lo pubblica python.org nel pacchetto embeddable.
PTH_ORIGINALE = "python312.zip\n.\n\n# Uncomment to run site.main() automatically\n#import site\n"


def test_pth_aggiunge_bundle_e_dipendenze() -> None:
    """Senza queste due righe l'interprete non vede ne' ernesto ne' le librerie."""
    righe = patched_pth(PTH_ORIGINALE).splitlines()
    assert ".." in righe
    assert "../lib" in righe


def test_pth_riattiva_site() -> None:
    """`import site` arriva commentato e va riattivato, non lasciato in entrambe le forme."""
    righe = patched_pth(PTH_ORIGINALE).splitlines()
    assert "import site" in righe
    assert "#import site" not in righe


def test_pth_conserva_la_libreria_standard() -> None:
    """Le righe originali restano: sono la stdlib del runtime."""
    righe = patched_pth(PTH_ORIGINALE).splitlines()
    assert righe[0] == "python312.zip"
    assert "." in righe


def test_i_segreti_non_entrano_nel_bundle() -> None:
    """Il bundle nasce per essere copiato altrove: le credenziali restano qui."""
    scartati = ignored("qualsiasi", [".env", "credentials.md", "soul.md", "identity.md"])
    assert scartati == {".env", "credentials.md"}


def test_le_cartelle_generate_non_entrano_nel_bundle() -> None:
    scartati = ignored("qualsiasi", ["__pycache__", "cli.py", ".ruff_cache"])
    assert scartati == {"__pycache__", ".ruff_cache"}


def test_sorgenti_senza_dati_di_sessione() -> None:
    """Log, memorie, salvataggi e test non fanno parte di cio' che si distribuisce."""
    assert not {"logs", "memories", "saves", "workspace", "tests", ".venv"} & set(SOURCES)
    assert ".env" in EXCLUDED
