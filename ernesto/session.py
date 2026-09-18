"""Stato di sessione, log JSONL e contabilita' dei costi."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    COMPACT_HEAD_CHARS,
    COMPACT_KEEP_RECENT,
    COMPACT_MIN_CHARS,
    COMPACT_SUMMARY_MAX_CHARS,
    LOG_CONTENT_LIMIT,
)
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

    def __init__(self, workdir: Path, secrets: list[str], stamp: str | None = None) -> None:
        log_dir = workdir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        # Lo stesso stamp del file di memoria di sessione, cosi' log e memoria si incrociano.
        stamp = stamp or f"{datetime.now():%Y%m%d_%H%M%S}"
        self.path = log_dir / f"session-{stamp}.jsonl"
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


SUMMARY_PROMPT = (
    "Riassumi in massimo 5 righe il risultato di uno strumento, per un agente che deve "
    "ricordare cosa ha gia' fatto. Scrivi cosa e' stato fatto e cosa e' emerso (dati "
    "concreti, nomi, numeri, esiti). Niente preamboli, niente commenti sul riassunto."
)


def summarize_with_llm(client: Any, model_id: str, content: str, name: str) -> str | None:
    """Riassunto di un risultato strumento generato da un modello. None su qualunque errore.

    Il chiamante ricade sul riassunto deterministico: un percorso il cui unico scopo e'
    risparmiare non deve poter far fallire il turno.
    """
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"Strumento: {name}\n\n{content[:COMPACT_SUMMARY_MAX_CHARS]}"},
            ],
            stream=False,
        )
        testo = (resp.choices[0].message.content or "").strip()
    except Exception:
        return None
    return testo or None


def compact_tool_results(
    messages: list[dict[str, Any]],
    keep_recent: int = COMPACT_KEEP_RECENT,
    summarizer: Callable[[str, str], str | None] | None = None,
) -> tuple[int, int]:
    """Riassume i risultati degli strumenti piu' vecchi di `keep_recent` giri.

    Riscrive SOLO il campo `content` dei messaggi con role="tool": nessun messaggio viene
    rimosso o spostato, nessun ruolo cambia. Cosi' le coppie assistant-con-tool_calls /
    tool restano accoppiate e `rewind_index` in run_turn resta valido.

    Il confine e' calcolato a granularita' di assistant message, non di indice assoluto:
    i risultati di uno stesso assistant sono tutti compattati o tutti intatti.

    Con `summarizer` il riassunto e' generato da un modello (vedi summarize_with_llm); se
    restituisce None si ricade sul riassunto deterministico.

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
        args = args_by_id.get(str(msg.get("tool_call_id")), "")
        riassunto = summarizer(content, name) if summarizer else None
        digest = f"{COMPACT_PREFIX} {name} {args}\n{riassunto}" if riassunto else _digest(content, name, args)
        saved += estimate_tokens(content) - estimate_tokens(digest)
        msg["content"] = digest
        compacted += 1
    return compacted, max(saved, 0)


def session_snapshot(state: SessionState) -> dict[str, Any]:
    """Istantanea ricaricabile della sessione: messaggi completi piu' metadati."""
    return {
        "versione": 1,
        "salvato": datetime.now().isoformat(timespec="seconds"),
        "modello": state.model.id,
        "json_mode": state.json_mode,
        "reasoning": state.reasoning_effort,
        "token": {"in": state.total_prompt_tokens, "out": state.total_completion_tokens},
        "costo": state.total_cost,
        "secondi": state.total_seconds,
        "log": str(state.logger.path) if state.logger else None,
        "messaggi": state.messages,
    }


def validate_snapshot(data: Any) -> str | None:
    """Verifica un'istantanea prima di sostituirci la storia. None se e' valida.

    Un file manomesso deve produrre un errore leggibile qui, non una richiesta che l'API
    rifiuta a meta' del primo turno.
    """
    if not isinstance(data, dict):
        return "il file non contiene un oggetto JSON"
    messages = data.get("messaggi")
    if not isinstance(messages, list) or not messages:
        return "nessun messaggio nel salvataggio"
    ruoli_validi = {"system", "user", "assistant", "tool"}
    dichiarati: set[str] = set()
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return f"messaggio {i} non e' un oggetto"
        ruolo = msg.get("role")
        if ruolo not in ruoli_validi:
            return f"messaggio {i}: ruolo sconosciuto ({ruolo!r})"
        for call in msg.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("id"):
                dichiarati.add(str(call["id"]))
        # Un risultato tool senza la chiamata che lo ha generato rende la storia invalida
        if ruolo == "tool" and str(msg.get("tool_call_id")) not in dichiarati:
            return f"messaggio {i}: risultato tool senza la chiamata corrispondente"
    return None


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


def fmt_duration(seconds: float) -> str:
    """Formatta una durata (es. 8,3s oppure 2m 05s): i decimi servono solo sotto il minuto."""
    if seconds < 60:
        return f"{seconds:.1f}s".replace(".", ",")
    minuti, resto = divmod(int(seconds), 60)
    return f"{minuti}m {resto:02d}s"


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
    last_seconds: float = 0.0    # durata dell'ultimo turno
    total_seconds: float = 0.0   # tempo speso nei turni dall'inizio della sessione
    tool_calls_count: int = 0
    compacted_count: int = 0    # risultati strumento riassunti nella sessione
    compacted_tokens: int = 0   # token stimati risparmiati (cumulativo)
    # Skill attive: i nomi, non i contenuti. I corpi si rileggono da disco quando si
    # compone il system prompt, cosi' una modifica alla skill ha effetto al turno dopo.
    loaded_skills: list[str] = field(default_factory=list)
    # Riassuntore LLM per la compattazione automatica: None = riassunto deterministico.
    # Viene impostato dal REPL solo dopo conferma dell'utente (compact.llm_summary).
    summarizer: Callable[[str, str], str | None] | None = None

    def system_prompt(self) -> str:
        """System prompt completo per la configurazione corrente."""
        return compose_system_prompt(self.context, self.json_mode, self.loaded_skills)

    def refresh_system_prompt(self, force: bool = False) -> bool:
        """Ricompone messages[0] se l'indice delle memorie e' cambiato. True se aggiornato.

        Va chiamata una volta per turno, non a ogni step: cambiare il prefisso del prompt
        dentro il ciclo distruggerebbe il prompt caching del provider. Con `force` si
        ricompone comunque: serve dopo /skill, che cambia il prompt senza toccare le memorie.
        """
        cambiata = reload_memory(self.context)
        if not cambiata and not force:
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

    def record_time(self, seconds: float) -> None:
        """Registra la durata di un turno e aggiorna il cumulativo di sessione."""
        self.last_seconds = seconds
        self.total_seconds += seconds

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
