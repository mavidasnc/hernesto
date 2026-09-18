"""Strumenti Telegram via Bot API: invio al canale e lettura degli aggiornamenti ricevuti.

Credenziali (vedi credentials.md): TELEGRAM_BOT_TOKEN obbligatoria,
TELEGRAM_CHAT_ID come destinazione di default (il canale).

La lettura usa getUpdates: restituisce solo gli aggiornamenti recenti non ancora
scaduti (Telegram li conserva ~24 ore) e NON consuma la coda (nessun offset),
cosi' riletture successive vedono gli stessi messaggi. La cronologia di un canale
non e' accessibile con la Bot API.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from . import LEVEL_EXTERNAL, ConfirmFn, Tool

if TYPE_CHECKING:
    from ..session import SessionState

API_BASE = "https://api.telegram.org"
HTTP_TIMEOUT = 15.0
# Limite Telegram per messaggio: 4096 caratteri. Sopra, il testo va spezzato.
MAX_MESSAGE_CHARS = 4096
READ_MAX_LIMIT = 50
# Tetto del testo nel risultato di lettura: gli aggiornamenti restano leggibili
# senza riversare nella storia messaggi-fiume interi.
READ_TEXT_CHARS = 500


def _split_message(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Spezza il testo entro il limite Telegram, preferendo i confini di riga."""
    parts = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:  # nessun a-capo comodo: taglio netto
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    parts.append(rest)
    return parts


class TelegramSendTool(Tool):
    """Invia un messaggio a un canale/chat Telegram tramite il bot.

    Richiede conferma (saltata con --yolo). Testi oltre 4096 caratteri vengono
    spezzati in piu' messaggi sui confini di riga.
    """

    name = "telegram_send"
    description = (
        "Invia un messaggio Telegram tramite il bot (default: il canale TELEGRAM_CHAT_ID). "
        "Richiede conferma. parse_mode opzionale: HTML o MarkdownV2; markup non valido fa fallire l'invio."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Testo del messaggio"},
            "parse_mode": {
                "type": "string",
                "enum": ["", "HTML", "MarkdownV2"],
                "description": "Formattazione del testo (default: testo semplice)",
            },
            "chat_id": {
                "type": "string",
                "description": "Destinazione alternativa (default: TELEGRAM_CHAT_ID)",
            },
        },
        "required": ["text"],
    }

    def __init__(self, state: SessionState, confirm_fn: ConfirmFn) -> None:
        self._state = state
        self._confirm = confirm_fn

    def run(self, text: str, parse_mode: str = "", chat_id: str = "", **_: Any) -> str:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return "ERRORE: TELEGRAM_BOT_TOKEN non configurato (vedi credentials.md)."
        target = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        if not target:
            return "ERRORE: TELEGRAM_CHAT_ID non configurato: imposta il canale di default (vedi credentials.md)."
        if not text.strip():
            return "ERRORE: il messaggio e' vuoto."
        parts = _split_message(text)
        if self._state.dry_run:
            return f"DRY-RUN: messaggio Telegram simulato verso {target} ({len(parts)} parte/i, {len(text)} caratteri)"
        if not self._state.yolo:
            preview = f"A: {target}\n\n{text[:500]}"
            if len(text) > 500:
                preview += f"\n\n[+ altri {len(text) - 500} caratteri]"
            if len(parts) > 1:
                preview += f"\n(il testo verra' spezzato in {len(parts)} messaggi)"
            if not self._confirm("Inviare questo messaggio Telegram?", preview=preview, level=LEVEL_EXTERNAL):
                return "ERRORE: invio Telegram annullato dall'utente"
        ids = []
        for part in parts:
            body: dict[str, Any] = {"chat_id": target, "text": part}
            if parse_mode:
                body["parse_mode"] = parse_mode
            try:
                resp = httpx.post(f"{API_BASE}/bot{token}/sendMessage", json=body, timeout=HTTP_TIMEOUT)
                data = resp.json()
            except Exception as exc:
                return f"ERRORE: invio Telegram fallito: {exc}"
            if not data.get("ok"):
                # La risposta di errore di Telegram spiega il perche' (markup, chat_id, permessi)
                return f"ERRORE: Telegram ha rifiutato il messaggio: {data.get('description', data)}"
            ids.append(str(data["result"]["message_id"]))
        return f"Messaggio Telegram inviato a {target}. message_id: {', '.join(ids)}"


class TelegramReadTool(Tool):
    """Legge gli aggiornamenti ricevuti dal bot (messaggi diretti e post dei canali
    dove e' amministratore). Non consuma la coda e non accede alla cronologia."""

    name = "telegram_read"
    description = (
        "Legge gli ultimi aggiornamenti ricevuti dal bot Telegram (messaggi diretti, menzioni, "
        "post dei canali dove il bot e' amministratore). Solo aggiornamenti recenti (~24 ore), "
        "non la cronologia: Telegram conserva la coda getUpdates per un giorno."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": f"Numero massimo di aggiornamenti (default 10, massimo {READ_MAX_LIMIT})",
            },
        },
    }

    def run(self, limit: int = 10, **_: Any) -> str:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return "ERRORE: TELEGRAM_BOT_TOKEN non configurato (vedi credentials.md)."
        limit = max(1, min(limit, READ_MAX_LIMIT))
        try:
            resp = httpx.get(f"{API_BASE}/bot{token}/getUpdates", params={"limit": limit}, timeout=HTTP_TIMEOUT)
            data = resp.json()
        except Exception as exc:
            return f"ERRORE: lettura Telegram fallita: {exc}"
        if not data.get("ok"):
            return f"ERRORE: Telegram ha rifiutato la lettura: {data.get('description', data)}"
        updates = data.get("result", [])
        if not updates:
            return "Nessun aggiornamento recente per il bot."
        lines = []
        for update in updates:
            line = _format_update(update)
            if line:
                lines.append(line)
        return "\n".join(lines) if lines else "Aggiornamenti presenti ma nessun messaggio testuale."


def _format_update(update: dict[str, Any]) -> str | None:
    """Una riga per aggiornamento: data, chat, mittente e testo troncato."""
    msg = (
        update.get("message")
        or update.get("channel_post")
        or update.get("edited_message")
        or update.get("edited_channel_post")
    )
    if not msg:
        return None
    chat = msg.get("chat") or {}
    dove = chat.get("title") or chat.get("username") or chat.get("id", "?")
    mittente = (msg.get("from") or {}).get("first_name") or (msg.get("from") or {}).get("username") or "?"
    quando = datetime.fromtimestamp(msg.get("date", 0)).strftime("%Y-%m-%d %H:%M")
    testo = (msg.get("text") or msg.get("caption") or "(messaggio non testuale)").replace("\n", " ")
    if len(testo) > READ_TEXT_CHARS:
        testo = testo[:READ_TEXT_CHARS].rstrip() + "…"
    return f"[{quando}] {dove} · {mittente}: {testo}"
