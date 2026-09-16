"""Test per brave_search e send_email: API key mancante e mock HTTP."""

from __future__ import annotations

import pytest

from ernesto.session import SessionState
from ernesto.tools.mail import SendEmailTool
from ernesto.tools.web import BraveSearchTool


class FakeResponse:
    """Risposta HTTP finta per i test."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

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


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------


def test_send_email_missing_key(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza RESEND_API_KEY lo strumento restituisce un errore leggibile, zero crash."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    tool = SendEmailTool(state, lambda message, preview=None: True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert result.startswith("ERRORE")
    assert "RESEND_API_KEY" in result


def test_send_email_missing_from(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza RESEND_FROM lo strumento restituisce un errore leggibile."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    tool = SendEmailTool(state, lambda message, preview=None: True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "RESEND_FROM" in result


def test_send_email_refused(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Senza conferma dell'utente l'email non viene inviata."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    tool = SendEmailTool(state, lambda message, preview=None: False)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "annullato" in result


def test_send_email_ok(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Con chiavi e conferma, l'email viene inviata (mock HTTP) e restituisce l'id."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    monkeypatch.setattr("ernesto.tools.mail.httpx.post", lambda *a, **k: FakeResponse({"id": "msg_123"}))
    tool = SendEmailTool(state, lambda message, preview=None: True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert "msg_123" in result


def test_send_email_dry_run(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """In dry-run l'email e' solo simulata."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "chat@example.com")
    state.dry_run = True
    tool = SendEmailTool(state, lambda message, preview=None: True)
    result = tool.run(to="a@b.com", subject="s", text="t")
    assert result.startswith("DRY-RUN")
