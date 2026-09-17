"""Costruisce un bundle di ernesto che parte su Windows senza Python installato.

Il bundle contiene il runtime embeddable di python.org, le dipendenze di
`requirements.txt` e i sorgenti del progetto, e si avvia con il suo `ernesto.cmd`.
Si costruisce su Windows con lo stesso Python del bundle (3.12 a 64 bit), perche'
le dipendenze compilate arrivano come wheel scelti per l'interprete che li installa.

    python build_bundle.py                 # dist/ernesto/ e dist/ernesto-<ver>-win64.zip
    python build_bundle.py --no-zip        # solo la cartella
    python build_bundle.py --dest altrove  # cartella di destinazione diversa

Segreti esclusi: `.env` e `context/credentials.md` non entrano mai nel bundle, che
nasce per essere copiato su un altro computer.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from ernesto import __version__

# Versione del runtime: la serie 3.12 e' quella su cui il progetto gira ed e'
# l'ultima con i pacchetti embeddable pubblicati da python.org.
PYTHON_VERSION = "3.12.10"
EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"

ROOT = Path(__file__).resolve().parent

# Cio' che serve a ernesto per funzionare, e nient'altro: niente test, niente
# cronologia di sessione, niente credenziali.
SOURCES = (
    "ernesto",
    "ernesto.py",
    "context",
    "skills",
    "playbooks",
    "requirements.txt",
    "README.md",
    "LICENSE",
)

# File che non devono uscire dal computer su cui il bundle viene costruito, piu'
# le cartelle rigenerate da Python.
EXCLUDED = frozenset({".env", "credentials.md", "__pycache__", ".pytest_cache", ".ruff_cache"})

# Il launcher del bundle e' piu' corto di quello del repository: qui il runtime
# c'e' per definizione, non serve il ramo che ricostruisce un virtualenv.
LAUNCHER = """@echo off
rem Avvia ernesto con il runtime Python incluso nel bundle.
rem %~dp0 e' la cartella di questo file: il bundle si sposta dove si vuole.
setlocal
set "PYTHONIOENCODING=utf-8"
set "ERNESTO_HOME=%~dp0."
"%ERNESTO_HOME%\\runtime\\python.exe" "%ERNESTO_HOME%\\ernesto.py" %*
exit /b %errorlevel%
"""


def ignored(_directory: str, names: list[str]) -> set[str]:
    """Filtro per `shutil.copytree`: i nomi da non copiare nel bundle."""
    return {name for name in names if name in EXCLUDED}


def patched_pth(original: str) -> str:
    """Il percorso di ricerca del runtime embeddable, esteso al bundle.

    Il file `._pth` accanto a python.exe sostituisce il normale calcolo di
    `sys.path`: senza queste righe l'interprete vede solo la propria libreria
    standard, quindi ne' i sorgenti di ernesto ne' le dipendenze. I percorsi sono
    relativi alla cartella del runtime. `import site` va riattivato perche' molte
    librerie di terze parti lo danno per scontato.
    """
    righe = [riga for riga in original.splitlines() if riga.strip() != "#import site"]
    righe += ["..", "../lib", "import site"]
    return "\n".join(righe) + "\n"


def scarica_runtime(destinazione: Path) -> None:
    """Scarica il pacchetto embeddable e lo estrae in `destinazione`."""
    archivio = destinazione.parent / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if not archivio.exists():
        print(f"[bundle] scarico {EMBED_URL}")
        archivio.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(EMBED_URL, archivio)
    print(f"[bundle] estraggo il runtime in {destinazione}")
    with zipfile.ZipFile(archivio) as zf:
        zf.extractall(destinazione)
    archivio.unlink()

    pth = next(destinazione.glob("python*._pth"))
    pth.write_text(patched_pth(pth.read_text(encoding="utf-8")), encoding="utf-8")


def installa_dipendenze(lib: Path) -> None:
    """Installa `requirements.txt` in `lib`, come cartella piatta di pacchetti."""
    print(f"[bundle] installo le dipendenze in {lib}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--target",
            str(lib),
            "--requirement",
            str(ROOT / "requirements.txt"),
        ],
        check=True,
    )


def copia_sorgenti(bundle: Path) -> None:
    """Copia nel bundle i sorgenti elencati in `SOURCES`."""
    for nome in SOURCES:
        origine = ROOT / nome
        if not origine.exists():
            print(f"[bundle] salto {nome}: non esiste")
            continue
        if origine.is_dir():
            shutil.copytree(origine, bundle / nome, ignore=ignored)
        else:
            shutil.copy2(origine, bundle / nome)
    (bundle / "ernesto.cmd").write_text(LAUNCHER, encoding="ascii", newline="\r\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Costruisce il bundle autonomo di ernesto per Windows.")
    parser.add_argument("--dest", default="dist", help="cartella di destinazione (default: dist)")
    parser.add_argument("--no-zip", action="store_true", help="non creare l'archivio zip")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("[bundle] il bundle e' per Windows e va costruito su Windows.", file=sys.stderr)
        return 1

    dest = Path(args.dest).resolve()
    bundle = dest / "ernesto"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    scarica_runtime(bundle / "runtime")
    installa_dipendenze(bundle / "lib")
    copia_sorgenti(bundle)

    if not args.no_zip:
        archivio = dest / f"ernesto-{__version__}-win64"
        print(f"[bundle] creo {archivio}.zip")
        shutil.make_archive(str(archivio), "zip", root_dir=dest, base_dir="ernesto")

    print(f"[bundle] pronto: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
