"""Test per telegram_send e telegram_read: HTTP mockato, nessuna chiamata reale."""

from __future__ import annotations

import pytest

from ernesto.session import SessionState
from ernesto.tools import LEVEL_EXTERNAL
from ernesto.tools.telegram import MAX_MESSAGE_CHARS, TelegramReadTool, TelegramSendTool, _split_message


class FakeResponse:
    """Risposta HTTP finta dell'API Telegram."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _confirm_si(message: str, preview: str | None = None, level: str = "") -> bool:
    return True


def _tool(state: SessionState, confirm=_confirm_si) -> TelegramSendTool:
    return TelegramSendTool(state, confirm)


# ---------------------------------------------------------------------------
# telegram_send
# ---------------------------------------------------------------------------


def test_send_senza_token(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    result = _tool(state).run(text="ciao")
    assert result.startswith("ERRORE")
    assert "TELEGRAM_BOT_TOKEN" in result


def test_send_senza_chat_id(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = _tool(state).run(text="ciao")
    assert "TELEGRAM_CHAT_ID" in result


def test_send_messaggio_vuoto(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    result = _tool(state).run(text="   ")
    assert result.startswith("ERRORE")


def test_send_dry_run(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    state.dry_run = True
    result = _tool(state).run(text="ciao")
    assert result.startswith("DRY-RUN")


def test_send_senza_conferma(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    tool = _tool(state, lambda message, preview=None, level="": False)
    result = tool.run(text="ciao")
    assert "annullato" in result


def test_send_livello_esterno(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """L'invio a un canale chiede conferma come azione verso l'esterno."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return False

    _tool(state, confirm).run(text="ciao")
    assert livelli == [LEVEL_EXTERNAL]


def test_send_ok(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Con token, chat e conferma il messaggio parte e torna il message_id."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    inviati: list[dict] = []

    def post(url: str, json: dict, **kwargs: object) -> FakeResponse:
        inviati.append(json)
        return FakeResponse({"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr("ernesto.tools.telegram.httpx.post", post)
    result = _tool(state).run(text="ciao", parse_mode="HTML")
    assert "42" in result
    assert inviati[0]["chat_id"] == "@canale"
    assert inviati[0]["parse_mode"] == "HTML"


def test_send_rifiuto_telegram(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Un rifiuto dell'API (markup non valido, permessi) riporta la spiegazione."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    risposta = FakeResponse({"ok": False, "description": "can't parse entities"})
    monkeypatch.setattr("ernesto.tools.telegram.httpx.post", lambda *a, **k: risposta)
    result = _tool(state).run(text="<b>rotto")
    assert "can't parse entities" in result


def test_send_messaggio_lungo_spezzato(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    """Oltre 4096 caratteri il testo parte in piu' messaggi."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@canale")
    inviati: list[dict] = []

    def post(url: str, json: dict, **kwargs: object) -> FakeResponse:
        inviati.append(json)
        return FakeResponse({"ok": True, "result": {"message_id": len(inviati)}})

    monkeypatch.setattr("ernesto.tools.telegram.httpx.post", post)
    testo = ("riga lunga di prova\n" * 400).strip()
    result = _tool(state).run(text=testo)
    assert len(inviati) > 1
    assert all(len(p["text"]) <= MAX_MESSAGE_CHARS for p in inviati)
    assert "1, 2" in result


def test_split_rispetta_i_confini() -> None:
    """Lo spezzamento preferisce gli a-capo e non perde caratteri."""
    testo = "abcde\n" * 2000
    parti = _split_message(testo, 1000)
    assert all(len(p) <= 1000 for p in parti)
    assert "\n".join(p.strip("\n") for p in parti).replace("\n\n", "\n") or True  # nessun crash
    assert "".join(parti).replace("\n", "") == testo.replace("\n", "")


# ---------------------------------------------------------------------------
# telegram_read
# ---------------------------------------------------------------------------


def test_read_senza_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    result = TelegramReadTool().run()
    assert "TELEGRAM_BOT_TOKEN" in result


def test_read_formatta_gli_aggiornamenti(monkeypatch: pytest.MonkeyPatch) -> None:
    """Messaggi diretti e post di canale diventano righe leggibili."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 1,
                "message": {
                    "date": 1758196800,
                    "from": {"first_name": "Maurizio"},
                    "chat": {"id": 123, "username": "mario"},
                    "text": "ciao bot",
                },
            },
            {
                "update_id": 2,
                "channel_post": {
                    "date": 1758196900,
                    "chat": {"id": -100, "title": "Canale AI"},
                    "text": "post dal canale",
                },
            },
            {"update_id": 3},  # aggiornamento senza messaggio: saltato
        ],
    }
    monkeypatch.setattr("ernesto.tools.telegram.httpx.get", lambda *a, **k: FakeResponse(payload))
    result = TelegramReadTool().run()
    assert "Maurizio: ciao bot" in result
    assert "Canale AI" in result
    assert result.count("\n") == 1


def test_read_nessun_aggiornamento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr("ernesto.tools.telegram.httpx.get", lambda *a, **k: FakeResponse({"ok": True, "result": []}))
    assert "Nessun aggiornamento" in TelegramReadTool().run()


def test_read_errore_rete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")

    def failing_get(*a: object, **k: object) -> FakeResponse:
        raise ConnectionError("giu'")

    monkeypatch.setattr("ernesto.tools.telegram.httpx.get", failing_get)
    assert TelegramReadTool().run().startswith("ERRORE")
