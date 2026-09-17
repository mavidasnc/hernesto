#!/usr/bin/env bash
# Lancia ernesto con il Python del .venv del repository, da qualunque cartella (git bash, WSL).
# La cartella di lavoro resta quella corrente: e' la workdir dell'agente.
set -euo pipefail
ERNESTO_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for candidate in "$ERNESTO_HOME/.venv/Scripts/python.exe" "$ERNESTO_HOME/.venv/bin/python"; do
  if [ -x "$candidate" ]; then
    PYTHONIOENCODING=utf-8 exec "$candidate" "$ERNESTO_HOME/ernesto.py" "$@"
  fi
done
echo "[ernesto] virtualenv non trovato in $ERNESTO_HOME/.venv" >&2
echo "[ernesto] crealo con: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt" >&2
exit 1
