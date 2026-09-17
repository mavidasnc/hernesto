"""Test della compattazione della storia: invarianti, confini e idempotenza."""

from __future__ import annotations

from typing import Any

from ernesto.config import COMPACT_KEEP_RECENT
from ernesto.session import COMPACT_PREFIX, compact_tool_results, estimate_tokens

CONTENUTO_LUNGO = "riga di contenuto molto lunga\n" * 60  # ben oltre COMPACT_MIN_CHARS


def _storia(turni: int, tool_per_turno: int = 1, content: str = CONTENUTO_LUNGO) -> list[dict[str, Any]]:
    """Costruisce una storia con `turni` giri assistant(tool_calls) + risultati tool."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "prompt di sistema"},
        {"role": "user", "content": "domanda iniziale"},
    ]
    for t in range(turni):
        calls = [
            {
                "id": f"call_{t}_{n}",
                "type": "function",
                "function": {"name": "read_file", "arguments": f'{{"path": "file_{t}_{n}.py"}}'},
            }
            for n in range(tool_per_turno)
        ]
        messages.append({"role": "assistant", "content": None, "tool_calls": calls})
        for call in calls:
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "name": "read_file", "content": content}
            )
    messages.append({"role": "assistant", "content": "risposta finale"})
    return messages


def test_compact_preserves_pairing() -> None:
    """Lunghezza, ruoli e accoppiamento assistant/tool restano intatti."""
    messages = _storia(turni=8)
    prima_len = len(messages)
    prima_ruoli = [m["role"] for m in messages]
    prima_ids = [m.get("tool_call_id") for m in messages]
    compact_tool_results(messages)
    assert len(messages) == prima_len
    assert [m["role"] for m in messages] == prima_ruoli
    assert [m.get("tool_call_id") for m in messages] == prima_ids
    # ogni risultato tool segue un assistant che dichiara il suo tool_call_id
    for i, msg in enumerate(messages):
        if msg["role"] == "tool":
            chiamanti = [c["id"] for m in messages[:i] for c in (m.get("tool_calls") or [])]
            assert msg["tool_call_id"] in chiamanti


def test_compact_keeps_recent_intact() -> None:
    """Gli ultimi giri restano identici byte per byte."""
    messages = _storia(turni=8)
    compact_tool_results(messages, keep_recent=COMPACT_KEEP_RECENT)
    recenti = [m for m in messages if m["role"] == "tool"][-COMPACT_KEEP_RECENT:]
    assert all(m["content"] == CONTENUTO_LUNGO for m in recenti)


def test_compact_rewrites_old_tool_results() -> None:
    """I risultati vecchi diventano un riassunto che dice cosa era stato fatto."""
    messages = _storia(turni=8)
    compattati, _ = compact_tool_results(messages)
    assert compattati == 5  # 8 giri meno i 3 preservati
    vecchio = next(m for m in messages if m["role"] == "tool")
    assert vecchio["content"].startswith(COMPACT_PREFIX)
    assert "read_file" in vecchio["content"]
    assert "file_0_0.py" in vecchio["content"]
    assert len(vecchio["content"]) < len(CONTENUTO_LUNGO)


def test_compact_ignores_user_and_assistant() -> None:
    """System, user e assistant non vengono mai toccati."""
    messages = _storia(turni=8)
    prima = [m["content"] for m in messages if m["role"] != "tool"]
    compact_tool_results(messages)
    assert [m["content"] for m in messages if m["role"] != "tool"] == prima


def test_compact_is_idempotent() -> None:
    """Una seconda passata non trova piu' nulla da compattare."""
    messages = _storia(turni=8)
    compact_tool_results(messages)
    dopo_prima = [m["content"] for m in messages]
    assert compact_tool_results(messages) == (0, 0)
    assert [m["content"] for m in messages] == dopo_prima


def test_compact_skips_short_results() -> None:
    """Un risultato breve resta intatto: il riassunto non risparmierebbe nulla."""
    messages = _storia(turni=8, content="ok, 3 file trovati")
    assert compact_tool_results(messages) == (0, 0)


def test_compact_preserves_error_results() -> None:
    """Gli errori restano leggibili: servono al modello per non ripetere lo sbaglio."""
    messages = _storia(turni=8, content="ERRORE: file non trovato\n" + "dettaglio\n" * 60)
    assert compact_tool_results(messages) == (0, 0)


def test_compact_boundary_at_assistant_granularity() -> None:
    """Un assistant con piu' tool_calls e' compattato tutto o niente."""
    messages = _storia(turni=6, tool_per_turno=3)
    compact_tool_results(messages)
    for msg in messages:
        if not msg.get("tool_calls"):
            continue
        ids = [c["id"] for c in msg["tool_calls"]]
        risultati = [m["content"] for m in messages if m.get("tool_call_id") in ids]
        compattati = [c.startswith(COMPACT_PREFIX) for c in risultati]
        assert all(compattati) or not any(compattati)


def test_compact_returns_saved_tokens() -> None:
    """I token dichiarati coincidono con il risparmio reale sulla storia."""
    messages = _storia(turni=8)
    prima = sum(estimate_tokens(str(m.get("content") or "")) for m in messages)
    _, risparmiati = compact_tool_results(messages)
    dopo = sum(estimate_tokens(str(m.get("content") or "")) for m in messages)
    assert risparmiati > 0
    assert risparmiati == prima - dopo


def test_compact_noop_sotto_il_minimo_di_giri() -> None:
    """Con meno giri di keep_recent non si compatta nulla."""
    assert compact_tool_results(_storia(turni=COMPACT_KEEP_RECENT)) == (0, 0)
