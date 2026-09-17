"""Stato di sessione, log JSONL e contabilita' dei costi."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import COMPACT_HEAD_CHARS, COMPACT_KEEP_RECENT, COMPACT_MIN_CHARS, LOG_CONTENT_LIMIT
from .context import Context, compose_system_prompt, reload_memory
from .models import ModelConfig

COMPACT_PREFIX = "[compattato]"


def mask_secret(value: str) -> str:
    """Maschera un segreto nello stile `sk-or-…abcd` (primi 6 + ultimi 4 caratteri)."""
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}…{value[-4:]}"


class SessionLogger:
    """Scrive gli eventi della sessione in un file JSONL con masking dei segreti."""

    def __init__(self, workdir: Path, secrets: list[str]) -> None:
        log_dir = workdir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"session-{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        self._secrets = [s for s in secrets if s]

    def _mask(self, text: str) -> str:
        """Sostituisce i valori delle credenziali note con la forma mascherata."""
        for secret in self._secrets:
            text = text.replace(secret, mask_secret(secret))
        return text

    def log(self, event_type: str, **fields: Any) -> None:
        """Aggiunge un evento al log: timestamp ISO, contenuto troncato e mascherato."""
        event: dict[str, Any] = {"ts": datetime.now().isoformat(timespec="seconds"), "type": event_type}
        for key, value in fields.items():
            if isinstance(value, str):
                if key == "content" and len(value) > LOG_CONTENT_LIMIT:
                    value = value[:LOG_CONTENT_LIMIT] + "…[troncato]"
                value = self._mask(value)
            event[key] = value
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass  # il log non deve mai interrompere la sessione


def _tool_call_args(messages: list[dict[str, Any]]) -> dict[str, str]:
    """Mappa tool_call_id -> argomenti JSON, letti dagli assistant message."""
    args: dict[str, str] = {}
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            raw = (call.get("function") or {}).get("arguments") or ""
            args[call.get("id", "")] = raw[:120]
    return args


def _digest(content: str, name: str, args: str) -> str:
    """Riassunto deterministico di un risultato strumento.

    Non deve essere fedele: deve essere un puntatore. Il contenuto integrale resta nel
    log JSONL e i file si rileggono con read_file, quindi conservare nome, argomenti,
    dimensione, testa e ultima riga basta al modello per sapere cosa ha gia' fatto.
    """
    lines = content.splitlines()
    head = content[:COMPACT_HEAD_CHARS].strip()
    # L'ultima riga va limitata: un output senza a capo (JSON, HTML) sarebbe tutto "coda"
    # e il riassunto finirebbe per essere lungo quanto l'originale.
    tail = lines[-1].strip()[-COMPACT_HEAD_CHARS:] if lines else ""
    parts = [f"{COMPACT_PREFIX} {name} {args} · {len(content)} caratteri"]
    if head:
        parts.append(f"inizio: {head}")
    if tail and tail not in head:
        parts.append(f"fine: {tail}")
    parts.append("…[contenuto integrale nel log di sessione; rileggi la fonte se serve]")
    return "\n".join(parts)


def compact_tool_results(
    messages: list[dict[str, Any]],
    keep_recent: int = COMPACT_KEEP_RECENT,
) -> tuple[int, int]:
    """Riassume i risultati degli strumenti piu' vecchi di `keep_recent` giri.

    Riscrive SOLO il campo `content` dei messaggi con role="tool": nessun messaggio viene
    rimosso o spostato, nessun ruolo cambia. Cosi' le coppie assistant-con-tool_calls /
    tool restano accoppiate e `rewind_index` in run_turn resta valido.

    Il confine e' calcolato a granularita' di assistant message, non di indice assoluto:
    i risultati di uno stesso assistant sono tutti compattati o tutti intatti.

    Restituisce (messaggi compattati, token stimati risparmiati).
    """
    turns = [i for i, msg in enumerate(messages) if msg.get("tool_calls")]
    if len(turns) <= keep_recent:
        return 0, 0
    cutoff = turns[-keep_recent] if keep_recent else len(messages)
    args_by_id = _tool_call_args(messages)
    compacted = 0
    saved = 0
    for msg in messages[:cutoff]:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        # Gia' compattato, troppo corto o errore: lasciare stare. Gli errori sono brevi e
        # servono al modello per non ripetere lo stesso sbaglio.
        if content.startswith(COMPACT_PREFIX) or len(content) < COMPACT_MIN_CHARS or content.startswith("ERRORE"):
            continue
        name = str(msg.get("name") or "strumento")
        digest = _digest(content, name, args_by_id.get(str(msg.get("tool_call_id")), ""))
        saved += estimate_tokens(content) - estimate_tokens(digest)
        msg["content"] = digest
        compacted += 1
    return compacted, max(saved, 0)


def fmt_tokens(n: int) -> str:
    """Formatta un conteggio token con suffissi k/M (es. 24.1k, 1.2M)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_cost(cost: float) -> str:
    """Formatta un costo in USD (es. $0.0082)."""
    return f"${cost:.4f}"


def estimate_tokens(text: str) -> int:
    """Stima euristica dei token: ~4 caratteri per token."""
    return max(1, len(text) // 4)


@dataclass
class SessionState:
    """Stato completo della sessione: modello, messaggi, flag e conteggi cumulativi."""

    model: ModelConfig
    workdir: Path
    context: Context
    logger: SessionLogger | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    json_mode: bool = False
    yolo: bool = False
    dry_run: bool = False
    reasoning_effort: str = "medium"
    tools_enabled: bool = True  # False se il provider non supporta i tool (degradazione)
    last_prompt_tokens: int = 0
    last_completion_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    tool_calls_count: int = 0
    compacted_count: int = 0    # risultati strumento riassunti nella sessione
    compacted_tokens: int = 0   # token stimati risparmiati (cumulativo)

    def system_prompt(self) -> str:
        """System prompt completo per la configurazione corrente."""
        return compose_system_prompt(self.context, self.json_mode)

    def refresh_system_prompt(self) -> bool:
        """Ricarica memory.md e riscrive messages[0] se e' cambiata. True se aggiornato.

        Va chiamata una volta per turno, non a ogni step: cambiare il prefisso del prompt
        dentro il ciclo distruggerebbe il prompt caching del provider.
        """
        if not reload_memory(self.context):
            return False
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = self.system_prompt()
        return True

    def reset_messages(self) -> None:
        """Azzera la conversazione mantenendo il system prompt."""
        self.messages = [{"role": "system", "content": self.system_prompt()}]

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Registra l'usage di uno step e aggiorna i cumulativi. Restituisce il costo."""
        cost = prompt_tokens * self.model.price_prompt + completion_tokens * self.model.price_completion
        self.last_prompt_tokens = prompt_tokens
        self.last_completion_tokens = completion_tokens
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost += cost
        return cost

    def history_token_estimate(self) -> int:
        """Stima dei token occupati dai messaggi in storia."""
        return sum(estimate_tokens(str(m.get("content") or "")) for m in self.messages)


def prompt_indicator(state: SessionState) -> str:
    """Prompt di input con i cumulativi di sessione, es. `Tu [24.1k in · 6.3k out · $0.0082]> `."""
    flags = ""
    if state.yolo:
        flags += " · YOLO"
    if state.dry_run:
        flags += " · DRY"
    return (
        f"Tu [{fmt_tokens(state.total_prompt_tokens)} in · "
        f"{fmt_tokens(state.total_completion_tokens)} out · "
        f"{fmt_cost(state.total_cost)}{flags}]> "
    )
