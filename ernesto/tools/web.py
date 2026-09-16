"""Strumento di ricerca web tramite l'API Brave Search."""

from __future__ import annotations

import os
from typing import Any, ClassVar

import httpx

from . import Tool

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchTool(Tool):
    """Cerca sul web con Brave Search.

    Se BRAVE_API_KEY manca, lo strumento resta registrato ma restituisce un errore
    leggibile che spiega come configurarla.
    """

    name = "brave_search"
    description = "Cerca sul web con Brave Search; restituisce titolo, URL e snippet dei risultati."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query di ricerca"},
            "count": {"type": "integer", "description": "Numero di risultati (max 20)", "default": 10},
        },
        "required": ["query"],
    }

    def run(self, query: str, count: int = 10, **_: Any) -> str:
        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return (
                "ERRORE: BRAVE_API_KEY non configurata. Esporta la variabile d'ambiente "
                "(vedi credentials.md) per abilitare la ricerca web."
            )
        try:
            resp = httpx.get(
                BRAVE_SEARCH_URL,
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                params={"q": query, "count": int(count)},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return f"ERRORE: ricerca Brave fallita: {exc}"
        results = (data.get("web") or {}).get("results") or []
        if not results:
            return "Nessun risultato."
        lines = []
        for i, item in enumerate(results[: int(count)], 1):
            title = item.get("title", "(senza titolo)")
            url = item.get("url", "")
            snippet = item.get("description", "")
            lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
        return "\n".join(lines)
