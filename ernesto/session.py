"""Stato di sessione, log JSONL e contabilita' dei costi."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import LOG_CONTENT_LIMIT
from .context import Context, compose_system_prompt
from .models import ModelConfig


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

    def system_prompt(self) -> str:
        """System prompt completo per la configurazione corrente."""
        return compose_system_prompt(self.context, self.json_mode)

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
