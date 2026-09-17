"""Test per brave_search e send_email: API key mancante e mock HTTP."""

from __future__ import annotations

import pytest

from ernesto.session import SessionState
from ernesto.tools import LEVEL_EXTERNAL
from ernesto.tools.mail import SendEmailTool
from ernesto.tools.web import RATE_LIMIT_WAIT, BraveSearchTool, FetchUrlTool


class FakeResponse:
    """Risposta HTTP finta per i test."""

    def __init__(
        self,
        payload: dict | None = None,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        url: str = "https://example.com/",
    ) -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.url = url
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


# ---------------------------------------------------------------------------
# brave_search
# ---------------------------------------------------------------------------


def test_brave_search_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza BRAVE_API_KEY lo strumento restituisce un errore leggibile."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    result = BraveSearchTool().run(query="test")
    assert result.startswith("ERRORE")
    assert "BRAVE_API_KEY" in result


def test_brave_search_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con chiave configurata, i risultati vengono formattati (mock HTTP)."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    payload = {
        "web": {
            "results": [
                {"title": f"R{i}", "url": f"https://example.com/{i}", "description": f"snippet {i}"}
                for i in range(15)
            ]
        }
    }
    monkeypatch.setattr("ernesto.tools.web.httpx.get", lambda *a, **k: FakeResponse(payload))
    result = BraveSearchTool().run(query="qwen", count=10)
    assert "1. R0" in result
    assert "https://example.com/9" in result
    assert "R10" not in result  # limitato a count=10


def test_brave_search_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un errore HTTP viene convertito in stringa di errore."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")

    def failing_get(*args: object, **kwargs: object) -> FakeResponse:
        raise ConnectionError("rete giu'")

    monkeypatch.setattr("ernesto.tools.web.httpx.get", failing_get)
    result = BraveSearchTool().run(query="test")
    assert result.startswith("ERRORE")


def test_brave_retry_su_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un 429 viene ritentato una volta dopo l'attesa minima, poi la ricerca riesce."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    payload = {"web": {"results": [{"title": "R", "url": "https://e.com", "description": "s"}]}}
    risposte = [FakeResponse(status_code=429), FakeResponse(payload)]
    attese: list[float] = []
    monkeypatch.setattr("ernesto.tools.web.time.sleep", attese.append)
    monkeypatch.setattr("ernesto.tools.web.httpx.get", lambda *a, **k: risposte.pop(0))
    result = BraveSearchTool().run(query="test")
    assert "1. R" in result
    assert attese == [RATE_LIMIT_WAIT]


def test_brave_429_persistente_spiega_il_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se il 429 si ripete, l'errore nomina il limite invece di essere generico."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    monkeypatch.setattr("ernesto.tools.web.time.sleep", lambda _s: None)
    monkeypatch.setattr("ernesto.tools.web.httpx.get", lambda *a, **k: FakeResponse(status_code=429))
    result = BraveSearchTool().run(query="test")
    assert result.startswith("ERRORE")
    assert "1 richiesta al secondo" in result


def test_brave_snippet_senza_html(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il markup degli snippet non entra nel contesto del modello."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    payload = {
        "web": {
            "results": [
                {
                    "title": "Prezzi &amp; offerte",
                    "url": "https://e.com",
                    "description": "Sono <strong>gratis</strong> per tutti",
                }
            ]
        }
    }
    monkeypatch.setattr("ernesto.tools.web.httpx.get", lambda *a, **k: FakeResponse(payload))
    result = BraveSearchTool().run(query="test")
    assert "<strong>" not in result
    assert "Sono gratis per tutti" in result
    assert "Prezzi & offerte" in result


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------

PAGINA = b"""<html><head><title>Titolo pagina</title>
<style>body {color: red}</style></head>
<body><nav>menu da ignorare</nav>
<h1>Intestazione</h1><p>Primo paragrafo con &egrave; accentata.</p>
<script>var x = "codice da ignorare";</script>
<p>Secondo paragrafo.</p></body></html>"""


def _fake_html(monkeypatch: pytest.MonkeyPatch, content: bytes = PAGINA, content_type: str = "text/html") -> None:
    response = FakeResponse(content=content, headers={"content-type": content_type})
    monkeypatch.setattr("ernesto.tools.web.httpx.get", lambda *a, **k: response)


def test_fetch_url_estrae_testo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il testo visibile viene estratto; script, style e menu restano fuori."""
    _fake_html(monkeypatch)
    result = FetchUrlTool().run(url="https://example.com")
    assert "Titolo: Titolo pagina" in result
    assert "Primo paragrafo con è accentata." in result
    assert "Secondo paragrafo." in result
    assert "codice da ignorare" not in result
    assert "menu da ignorare" not in result
    assert "color: red" not in result
    assert "<p>" not in result


def test_fetch_url_content_type_rifiutato(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un PDF o un'immagine non vengono riversati nel contesto."""
    _fake_html(monkeypatch, content=b"%PDF-1.7", content_type="application/pdf")
    result = FetchUrlTool().run(url="https://example.com/doc.pdf")
    assert result.startswith("ERRORE")
    assert "non testuale" in result


def test_fetch_url_schema_rifiutato() -> None:
    """Sono ammessi solo http e https."""
    assert FetchUrlTool().run(url="file:///etc/passwd").startswith("ERRORE")


def test_fetch_url_errore_rete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un errore di rete diventa una stringa di errore, nessuna eccezione."""

    def failing_get(*args: object, **kwargs: object) -> FakeResponse:
        raise ConnectionError("rete giu'")

    monkeypatch.setattr("ernesto.tools.web.httpx.get", failing_get)
    result = FetchUrlTool().run(url="https://example.com")
    assert result.startswith("ERRORE")


def test_fetch_url_tronca(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oltre max_chars il testo viene troncato con nota."""
    lungo = b"<html><body><p>" + b"parola " * 2000 + b"</p></body></html>"
    _fake_html(monkeypatch, content=lungo)
    result = FetchUrlTool().run(url="https://example.com", max_chars=200)
    assert "troncato" in result
    assert len(result) < 500


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------


def test_send_email_missing_key(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza RESEND_API_KEY lo strumento restituisce un errore leggibile, zero crash."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    tool = SendEmailTool(state, lambda message, preview=None, level='': True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert result.startswith("ERRORE")
    assert "RESEND_API_KEY" in result


def test_send_email_missing_from(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza RESEND_FROM lo strumento restituisce un errore leggibile."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    tool = SendEmailTool(state, lambda message, preview=None, level='': True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "RESEND_FROM" in result


def test_send_email_refused(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza conferma dell'utente l'email non viene inviata."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    tool = SendEmailTool(state, lambda message, preview=None, level='': False)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "annullato" in result


def test_send_email_ok(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Con chiavi e conferma, l'email viene inviata (mock HTTP) e restituisce l'id."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    monkeypatch.setattr("ernesto.tools.mail.httpx.post", lambda *a, **k: FakeResponse({"id": "msg_123"}))
    tool = SendEmailTool(state, lambda message, preview=None, level='': True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "msg_123" in result


def test_send_email_dry_run(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """In dry-run l'email e' solo simulata."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    state.dry_run = True
    tool = SendEmailTool(state, lambda message, preview=None, level='': True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert result.startswith("DRY-RUN")


def test_send_email_livello_esterno(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """L'email chiede conferma come azione verso l'esterno, non come distruttiva."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return False

    SendEmailTool(state, confirm).run(to="a@b.com", subject="x", text="y")
    assert livelli == [LEVEL_EXTERNAL]
