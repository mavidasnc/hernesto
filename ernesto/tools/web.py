"""Strumenti web: ricerca via Brave Search e lettura del testo di una pagina."""

from __future__ import annotations

import os
import re
import time
from html import unescape
from html.parser import HTMLParser
from typing import Any, ClassVar

import httpx

from . import Tool

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
RATE_LIMIT_STATUS = 429
RATE_LIMIT_WAIT = 1.1  # il piano gratuito consente 1 richiesta al secondo

USER_AGENT = "ernesto/0.2 (+https://github.com/mavidasnc/ernesto)"
FETCH_TIMEOUT = 20.0
FETCH_MAX_BYTES = 2_000_000  # tetto sul download, prima ancora di decodificare
FETCH_DEFAULT_CHARS = 6000
TEXTUAL_TYPES = ("text/", "application/json", "application/xml", "application/xhtml")

_TAG_RE = re.compile(r"<[^>]+>")
_SPACES_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    """Rimuove i tag HTML e decodifica le entita' (per gli snippet di Brave)."""
    return unescape(_TAG_RE.sub("", text)).strip()


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
        headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
        params = {"q": query, "count": int(count)}
        # Il piano gratuito consente 1 richiesta al secondo: nel loop agentico due ricerche
        # consecutive partono a pochi millisecondi di distanza e la seconda prende 429.
        # Un solo nuovo tentativo dopo l'attesa minima basta a coprire il caso.
        for attempt in (1, 2):
            try:
                resp = httpx.get(BRAVE_SEARCH_URL, headers=headers, params=params, timeout=15.0)
                if resp.status_code == RATE_LIMIT_STATUS and attempt == 1:
                    time.sleep(RATE_LIMIT_WAIT)
                    continue
                if resp.status_code == RATE_LIMIT_STATUS:
                    return (
                        "ERRORE: limite di frequenza Brave superato (1 richiesta al secondo sul piano "
                        "gratuito). Aspetta un istante e rifai una sola ricerca, piu' mirata."
                    )
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                return f"ERRORE: ricerca Brave fallita: {exc}"
        results = (data.get("web") or {}).get("results") or []
        if not results:
            return "Nessun risultato."
        lines = []
        for i, item in enumerate(results[: int(count)], 1):
            title = strip_html(item.get("title", "")) or "(senza titolo)"
            url = item.get("url", "")
            # Gli snippet arrivano con markup (<strong>): senza pulizia entra nel contesto
            # come rumore a ogni ricerca.
            snippet = strip_html(item.get("description", ""))
            lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
        return "\n".join(lines)


class _TextExtractor(HTMLParser):
    """Estrae il testo visibile da una pagina HTML.

    Salta il contenuto dei tag di servizio (script, style, nav, footer, ...) e inserisce
    un a capo dopo i blocchi, cosi' il testo resta leggibile. Usa html.parser della
    stdlib: selectolax o readability darebbero un risultato migliore, ma il caso d'uso
    (dare al modello il testo di una pagina) non giustifica una dipendenza in piu'.
    """

    SKIP = frozenset({"script", "style", "noscript", "nav", "footer", "header", "form", "svg"})
    BLOCKS = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        # Solo il primo <title> fuori dai tag saltati: le icone SVG ne hanno uno ciascuna
        # e finirebbero tutte accodate al titolo della pagina.
        elif tag == "title" and not self._skip_depth and not self.title:
            self._in_title = True
        elif tag in self.BLOCKS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCKS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        elif not self._skip_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        """Il testo raccolto, con spazi e righe vuote collassati."""
        joined = _SPACES_RE.sub(" ", "".join(self._parts))
        lines = [line.strip() for line in joined.splitlines()]
        return _BLANK_LINES_RE.sub("\n\n", "\n".join(line for line in lines if line))


class FetchUrlTool(Tool):
    """Scarica una pagina web e ne restituisce il testo leggibile."""

    name = "fetch_url"
    description = (
        "Scarica una pagina web e restituisce il testo leggibile (senza HTML, script e menu). "
        "Da usare dopo brave_search per leggere davvero il contenuto di un risultato."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL completo (http o https)"},
            "max_chars": {
                "type": "integer",
                "description": f"Caratteri massimi di testo restituiti (default {FETCH_DEFAULT_CHARS})",
                "default": FETCH_DEFAULT_CHARS,
            },
        },
        "required": ["url"],
    }

    def run(self, url: str, max_chars: int = FETCH_DEFAULT_CHARS, **_: Any) -> str:
        if not url.lower().startswith(("http://", "https://")):
            return "ERRORE: sono ammessi solo URL http:// o https://"
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"},
                follow_redirects=True,
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            return f"ERRORE: download fallito: {exc}"
        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith(TEXTUAL_TYPES):
            return f"ERRORE: contenuto non testuale ({content_type or 'tipo sconosciuto'}): lettura rifiutata"
        raw = resp.content[:FETCH_MAX_BYTES]
        body = raw.decode(resp.encoding or "utf-8", errors="replace")
        if "html" in content_type:
            parser = _TextExtractor()
            parser.feed(body)
            title, text = parser.title, parser.text()
        else:
            title, text = "", body.strip()
        note = ""
        limit = int(max_chars)
        if len(text) > limit:
            text = text[:limit]
            note = f"\n…[testo troncato a {limit} caratteri: rilancia con max_chars piu' alto se serve]"
        header = f"URL: {resp.url}"
        if title:
            header += f"\nTitolo: {title}"
        return f"{header}\n\n{text}{note}"
