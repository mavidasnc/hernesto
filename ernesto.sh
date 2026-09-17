#!/usr/bin/env bash
# Lancia ernesto con il Python del .venv del repository, da qualunque cartella (git bash, WSL).
# La cartella di lavoro resta quella corrente: e' la workdir dell'agente.
set -uo pipefail
ERNESTO_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Un virtualenv non contiene l'interprete: il suo python e' un guscio che cerca la
# libreria standard nel percorso assoluto scritto in pyvenv.cfg. Copiata la cartella
# su un altro computer quel percorso non esiste piu', quindi il candidato non si
# controlla con -x soltanto: lo si avvia.
venv_python() {
  local candidate
  for candidate in "$ERNESTO_HOME/.venv/Scripts/python.exe" "$ERNESTO_HOME/.venv/bin/python"; do
    if [ -x "$candidate" ] && "$candidate" -c "" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

# Il Python di questo computer, con cui ricostruire il virtualenv. I candidati non
# sono quotati apposta: "py -3" e' comando piu' argomento.
host_python() {
  local candidate
  for candidate in "py -3" python3 python; do
    if $candidate -c "" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON="$(venv_python)"; then
  echo "[ernesto] virtualenv assente o inutilizzabile su questo computer: lo ricostruisco." >&2
  if ! HOST_PY="$(host_python)"; then
    echo "[ernesto] nessun Python utilizzabile nel PATH: installalo e rilancia questo comando." >&2
    exit 1
  fi
  rm -rf "$ERNESTO_HOME/.venv"
  $HOST_PY -m venv "$ERNESTO_HOME/.venv" || { echo "[ernesto] creazione del virtualenv fallita." >&2; exit 1; }
  PYTHON="$(venv_python)" || { echo "[ernesto] il virtualenv appena creato non parte." >&2; exit 1; }
  echo "[ernesto] installo le dipendenze da requirements.txt..." >&2
  "$PYTHON" -m pip install --quiet --disable-pip-version-check -r "$ERNESTO_HOME/requirements.txt" \
    || { echo "[ernesto] installazione delle dipendenze fallita: serve una connessione a internet." >&2; exit 1; }
  echo "[ernesto] virtualenv pronto." >&2
fi

PYTHONIOENCODING=utf-8 exec "$PYTHON" "$ERNESTO_HOME/ernesto.py" "$@"
