"""Installa i file di contesto di base in ~/.config/ernesto/.

I file canonici e versionati stanno in `context/`: da li' vengono copiati nella cartella di
configurazione, dove ernesto li trova qualunque sia la cartella di lavoro. Cosi' le regole
di base valgono anche sui progetti reali senza copiarle dentro ogni repository.

    python install-context.py            # copia, chiedendo prima di sovrascrivere
    python install-context.py --force    # sovrascrive senza chiedere
    python install-context.py --diff     # mostra solo cosa cambierebbe
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).parent / "context"
FILES = ("soul.md", "agent.md", "config.yaml")


def config_dir() -> Path:
    """La stessa cartella che cerca ernesto (vedi ernesto/config.py)."""
    return Path.home() / ".config" / "ernesto"


def main() -> int:
    parser = argparse.ArgumentParser(description="Installa i file di contesto di ernesto.")
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
        if dst.is_file() and dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"):
            print(f"= {name} gia' aggiornato")
            continue
        if args.diff:
            stato = "da aggiornare" if dst.is_file() else "da creare"
            print(f"! {name} {stato} in {target}")
            continue
        if dst.is_file() and not args.force:
            risposta = input(f"{name} esiste gia' in {target}. Sovrascrivere? (s/N) ").strip().lower()
            if risposta not in {"s", "si", "y", "yes"}:
                print(f"- {name} lasciato invariato")
                continue
        shutil.copy2(src, dst)
        print(f"+ {name} -> {dst}")

    if not args.diff:
        print(f"\nFatto. Da ora le istruzioni di base valgono in ogni cartella di lavoro ({target}).")
        print("Un agent.md dentro un progetto si somma a queste, non le sostituisce.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
