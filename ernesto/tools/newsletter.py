"""Strumento di lettura dell'archivio articoli del progetto newsletter.

Interroga `query_articles.py` (script stdlib-only del progetto parallelo
`newsletter`) tramite subprocess con l'interprete corrente: il DB SQLite resta
nel progetto che lo produce e qui passa solo l'output gia' filtrato.

La cartella del progetto si configura in `context/config.yaml`:

    newsletter:
      dir: C:/percorso/assoluto/newsletter
      days: 4

`days` e' la finestra temporale predefinita (articoli degli ultimi N giorni);
senza config si usa 4 e, come cartella, `../newsletter` rispetto alla workdir.

La marcatura `mark_processed` scrive sul DB esterno: chiede conferma
(LEVEL_WARNING) e in dry-run si limita a simulare.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..config import config_section
from . import LEVEL_WARNING, ConfirmFn, Tool

if TYPE_CHECKING:
    from ..session import SessionState

DEFAULT_DAYS = 4
DEFAULT_LIMIT = 100
# Tetto per articolo quando si chiede il contenuto: per valutare e riassumere
# bastano i primi paragrafi, e 20 articoli integrali da 10.000 caratteri
# saturerebbero la storia a ogni step successivo del loop.
FULL_CONTENT_CHARS = 2000
# Tetto complessivo dell'output: piu' generoso di TOOL_OUTPUT_LIMIT perche'
# la fase di lettura deve vedere tutta la shortlist in un colpo solo.
OUTPUT_CHARS = 50_000
QUERY_TIMEOUT = 60.0


class NewsletterQueryTool(Tool):
    """Interroga il DB degli articoli raccolti dal progetto newsletter."""

    name = "newsletter_query"
    description = (
        "Interroga l'archivio degli articoli AI raccolti dal progetto newsletter (DB SQLite). "
        "Di default restituisce gli articoli non ancora processati degli ultimi giorni, con estratto di "
        "300 caratteri: usa gli id per rileggere i contenuti estesi dei soli articoli scelti. "
        "Con mark_processed=true marca processed=1 sulla selezione (chiede conferma)."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": (
                    "Finestra in giorni indietro da oggi (default da config.yaml, altrimenti 4). "
                    "Ignorato se passi ids."
                ),
            },
            "processed": {
                "type": "string",
                "enum": ["0", "1", "all"],
                "description": "Filtro sul flag di elaborazione (default: 0 = da elaborare)",
            },
            "source": {
                "type": "string",
                "description": "Filtro per fonte (substring, case-insensitive)",
            },
            "ids": {
                "type": "string",
                "description": "Solo questi id articolo, CSV (es. \"12,34,56\"). Sostituisce il filtro temporale.",
            },
            "full_content": {
                "type": "boolean",
                "description": "Includi il contenuto esteso (primi 2000 caratteri per articolo) invece dell'estratto",
            },
            "count_only": {
                "type": "boolean",
                "description": "Restituisci solo il numero di articoli trovati",
            },
            "limit": {
                "type": "integer",
                "description": "Numero massimo di articoli (default 100)",
            },
            "mark_processed": {
                "type": "boolean",
                "description": (
                    "Marca processed=1 sugli articoli della selezione, dopo averli usati. "
                    "Per la rassegna marca l'intero lotto (stesso days, SENZA ids), mai i soli articoli inviati."
                ),
            },
        },
    }

    def __init__(self, state: SessionState, confirm_fn: ConfirmFn) -> None:
        self._state = state
        self._confirm = confirm_fn

    def _project_dir(self) -> Path:
        configured = config_section(self._state.workdir, "newsletter").get("dir")
        if configured:
            return Path(str(configured)).expanduser()
        return self._state.workdir.parent / "newsletter"

    def _default_days(self) -> int:
        configured = config_section(self._state.workdir, "newsletter").get("days")
        try:
            return int(configured)
        except (TypeError, ValueError):
            return DEFAULT_DAYS

    def run(
        self,
        days: int = 0,
        processed: str = "0",
        source: str = "",
        ids: str = "",
        full_content: bool = False,
        count_only: bool = False,
        limit: int = DEFAULT_LIMIT,
        mark_processed: bool = False,
        **_: Any,
    ) -> str:
        project_dir = self._project_dir()
        script = project_dir / "query_articles.py"
        if not script.is_file():
            return (
                f"ERRORE: script non trovato: {script}. "
                "Configura newsletter.dir in context/config.yaml con il percorso del progetto newsletter."
            )
        days = days or self._default_days()

        argv = [sys.executable, str(script), "--format", "json", "--processed", processed]
        if ids:
            argv += ["--ids", ids]
        else:
            until = date.today()
            since = until - timedelta(days=days)
            argv += ["--since", since.isoformat(), "--until", until.isoformat()]
        if source:
            argv += ["--source", source]
        if full_content:
            argv.append("--full-content")
        if count_only or mark_processed:
            # Con --count lo script ignora il LIMIT: il numero e' reale e, in
            # marcatura, l'UPDATE copre l'intera selezione invece dei primi N.
            argv.append("--count")
        argv += ["--limit", str(limit)]

        if mark_processed:
            selezione = f"ids {ids}" if ids else f"ultimi {days} giorni"
            if self._state.dry_run:
                return f"DRY-RUN: marcatura processed=1 simulata sulla selezione ({selezione})"
            if not self._state.yolo:
                preview = f"Selezione: {selezione}"
                if not self._confirm(
                    "Marcare come processati questi articoli nel DB newsletter?",
                    preview=preview,
                    level=LEVEL_WARNING,
                ):
                    return "ERRORE: marcatura annullata dall'utente"
            argv.append("--mark-processed")

        try:
            proc = subprocess.run(
                argv,
                cwd=project_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=QUERY_TIMEOUT,
            )
        except Exception as exc:
            return f"ERRORE: esecuzione di query_articles.py fallita: {exc}"
        if proc.returncode != 0:
            return f"ERRORE: query_articles.py (exit {proc.returncode}): {proc.stderr.strip()}"
        out = proc.stdout.strip()
        if not out:
            return proc.stderr.strip() or "Nessun articolo trovato con questi filtri."
        if count_only or mark_processed:
            note = proc.stderr.strip()
            return f"{out}\n{note}".strip() if note else out
        return self._trim(out, full_content)

    @staticmethod
    def _trim(out: str, full_content: bool) -> str:
        """Riduce i contenuti per articolo e l'output complessivo, senza spezzare il JSON."""
        try:
            rows = json.loads(out)
        except json.JSONDecodeError:
            return out[:OUTPUT_CHARS]
        if full_content and isinstance(rows, list):
            for row in rows:
                text = row.get("content_text")
                if isinstance(text, str) and len(text) > FULL_CONTENT_CHARS:
                    row["content_text"] = text[:FULL_CONTENT_CHARS].rstrip() + "…"
        result = json.dumps(rows, ensure_ascii=False, indent=2)
        if len(result) > OUTPUT_CHARS:
            result = result[:OUTPUT_CHARS] + "\n…[output troncato: restringi la selezione con ids o limit]"
        return result
