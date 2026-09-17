"""Strumento di invio email tramite l'API Resend."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from . import ConfirmFn, Tool

if TYPE_CHECKING:
    from ..session import SessionState

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM_NAME = "Chat CLI"


class SendEmailTool(Tool):
    """Invia una email via Resend. Richiede conferma interattiva (saltata con --yolo).

    RESEND_FROM puo' contenere l'indirizzo semplice (chat@example.com, completato con
    from_name) oppure gia' la forma completa `Nome <chat@example.com>`.
    Se il modello non passa from_name, si usa RESEND_FROM_NAME e, in mancanza, DEFAULT_FROM_NAME.
    """

    name = "send_email"
    description = "Invia una email tramite l'API Resend. Richiede conferma dell'utente."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Indirizzo email del destinatario"},
            "subject": {"type": "string", "description": "Oggetto della email"},
            "text": {"type": "string", "description": "Corpo della email (testo semplice)"},
            "from_name": {
                "type": "string",
                "description": "Nome del mittente (default: RESEND_FROM_NAME)",
            },
        },
        "required": ["to", "subject", "text"],
    }

    def __init__(self, state: SessionState, confirm_fn: ConfirmFn) -> None:
        self._state = state
        self._confirm = confirm_fn

    def run(self, to: str, subject: str, text: str, from_name: str = "", **_: Any) -> str:
        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            return "ERRORE: RESEND_API_KEY non configurata (vedi credentials.md)."
        sender = os.environ.get("RESEND_FROM")
        if not sender:
            return "ERRORE: RESEND_FROM non configurata: imposta l'indirizzo mittente (vedi credentials.md)."
        if self._state.dry_run:
            return f"DRY-RUN: email simulata a {to} (oggetto: {subject})"
        if not self._state.yolo:
            preview = f"A: {to}\nOggetto: {subject}\n\n{text[:500]}"
            if not self._confirm("Inviare questa email?", preview=preview):
                return "ERRORE: invio email annullato dall'utente"
        name = from_name or os.environ.get("RESEND_FROM_NAME") or DEFAULT_FROM_NAME
        from_field = sender if "<" in sender else f"{name} <{sender}>"
        body = {"from": from_field, "to": [to], "subject": subject, "text": text}
        try:
            resp = httpx.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return f"ERRORE: invio email fallito: {exc}"
        return f"Email inviata a {to}. id: {data.get('id', '(nessun id)')}"
