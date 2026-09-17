"""Installa il contesto di base in ~/.config/ernesto/context/ e prepara le cartelle di lavoro.

I file canonici e versionati stanno in `context/` di questo repository: da li' vengono
copiati nella cartella di configurazione, dove ernesto li trova qualunque sia la cartella di
lavoro. Cosi' le regole di base valgono anche sui progetti reali senza copiarle dentro ogni
repository.

`context/identity.md` contiene anche una sezione specifica del progetto ernesto, delimitata
dai marcatori `solo-progetto`: viene esclusa dalla copia globale, altrimenti i comandi di
test di questo repository finirebbero nel prompt di ogni altro progetto.

    python install-context.py            # copia, chiedendo prima di sovrascrivere
    python install-context.py --force    # sovrascrive senza chiedere
    python install-context.py --diff     # mostra solo cosa cambierebbe
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).parent / "context"
FILES = ("soul.md", "identity.md", "config.yaml")
WORK_DIRS = ("workspace/projects", "memories")

# Il blocco fra questi marcatori riguarda solo il repository di ernesto e non viene copiato.
ONLY_PROJECT_RE = re.compile(
    r"\n?<!-- solo-progetto: inizio.*?-->.*?<!-- solo-progetto: fine -->\n?",
    re.DOTALL,
)


def config_dir() -> Path:
    """La stessa cartella che cerca ernesto (vedi CONTEXT_DIR in ernesto/config.py)."""
    return Path.home() / ".config" / "ernesto" / "context"


def content_for_global(src: Path) -> str:
    """Contenuto da installare: senza le sezioni riservate a questo repository."""
    return ONLY_PROJECT_RE.sub("\n", src.read_text(encoding="utf-8")).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Installa il contesto di base di ernesto.")
    parser.add_argument("--force", action="store_true", help="sovrascrive senza chiedere")
    parser.add_argument("--diff", action="store_true", help="mostra le differenze senza copiare")
    args = parser.parse_args()

    target = config_dir()
    if not args.diff:
        target.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        src = SOURCE / name
        if not src.is_file():
            print(f"[Avviso] {src} non trovato: salto.")
            continue
        dst = target / name
        nuovo = content_for_global(src)
        if dst.is_file() and dst.read_text(encoding="utf-8") == nuovo:
            print(f"= {name} gia' aggiornato")
            continue
        if args.diff:
            print(f"! {name} {'da aggiornare' if dst.is_file() else 'da creare'} in {target}")
            continue
        if dst.is_file() and not args.force:
            risposta = input(f"{name} esiste gia' in {target}. Sovrascrivere? (s/N) ").strip().lower()
            if risposta not in {"s", "si", "y", "yes"}:
                print(f"- {name} lasciato invariato")
                continue
        dst.write_text(nuovo, encoding="utf-8")
        print(f"+ {name} -> {dst}")

    # Cartelle di lavoro: non stanno in git, quindi vanno ricreate dopo ogni clone
    base = Path(__file__).parent
    for rel in WORK_DIRS:
        d = base / rel
        if d.is_dir():
            print(f"= {rel}/ gia' presente")
        elif args.diff:
            print(f"! {rel}/ da creare in {base}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"+ {rel}/ -> {d}")

    if not args.diff:
        print(f"\nFatto. Le istruzioni di base valgono ora in ogni cartella di lavoro ({target}).")
        print("Un identity.md dentro un progetto si somma a queste, non le sostituisce.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
