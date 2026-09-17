"""Test per log JSONL, memoria nel prompt, salvataggio/ripresa e riassunto LLM."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ernesto.session import (
    COMPACT_PREFIX,
    SessionLogger,
    SessionState,
    compact_tool_results,
    fmt_tokens,
    mask_secret,
    session_snapshot,
    summarize_with_llm,
    validate_snapshot,
)

SECRET = "sk-or-v1-abcdef1234567890segreto9999"


def test_mask_secret_format() -> None:
    """Il masking usa la forma primi 6 + … + ultimi 4."""
    assert mask_secret(SECRET) == f"{SECRET[:6]}…{SECRET[-4:]}"
    assert mask_secret("corta") == "***"


def test_log_masks_secrets(tmp_path: Path) -> None:
    """I valori delle credenziali non compaiono mai in chiaro nel log."""
    logger = SessionLogger(tmp_path, [SECRET])
    logger.log("tool", name="run_command", content=f"output con {SECRET} dentro")
    raw = logger.path.read_text(encoding="utf-8")
    assert SECRET not in raw
    assert mask_secret(SECRET) in raw


def test_log_truncates_content(tmp_path: Path) -> None:
    """Il contenuto degli eventi e' troncato a 4000 caratteri."""
    logger = SessionLogger(tmp_path, [])
    logger.log("assistant", content="x" * 10000)
    event = json.loads(logger.path.read_text(encoding="utf-8").strip())
    assert len(event["content"]) < 4100
    assert event["content"].endswith("[troncato]")


def test_log_event_fields(tmp_path: Path) -> None:
    """Ogni evento ha timestamp ISO, tipo e campi extra."""
    logger = SessionLogger(tmp_path, [])
    logger.log("user", content="ciao", usage={"prompt": 10, "completion": 5})
    event = json.loads(logger.path.read_text(encoding="utf-8").strip())
    assert event["type"] == "user"
    assert event["content"] == "ciao"
    assert event["usage"] == {"prompt": 10, "completion": 5}
    assert "ts" in event


def test_fmt_tokens() -> None:
    """Formattazione k/M dei conteggi token."""
    assert fmt_tokens(340) == "340"
    assert fmt_tokens(24100) == "24.1k"
    assert fmt_tokens(1_200_000) == "1.2M"


def test_refresh_system_prompt_updates_message_zero(state: SessionState) -> None:
    """La memoria scritta dall'agente rientra nel prompt senza toccare la storia."""
    state.messages.append({"role": "user", "content": "domanda"})
    prima = list(state.messages[1:])
    memories = state.workdir / "memories"
    memories.mkdir(exist_ok=True)
    (memories / "memory.md").write_text("Deploy solo il martedi'.", encoding="utf-8")
    assert state.refresh_system_prompt() is True
    assert "Deploy solo il martedi'." in state.messages[0]["content"]
    assert state.messages[1:] == prima
    assert state.refresh_system_prompt() is False


def test_clear_keeps_memory(state: SessionState) -> None:
    """Dopo /clear la memoria e' ancora nel system prompt."""
    memories = state.workdir / "memories"
    memories.mkdir(exist_ok=True)
    (memories / "memory.md").write_text("Fatto da ricordare.", encoding="utf-8")
    state.refresh_system_prompt()
    state.reset_messages()
    assert "Fatto da ricordare." in state.messages[0]["content"]


# ---------------------------------------------------------------------------
# salvataggio e ripresa
# ---------------------------------------------------------------------------


def _storia_con_tool_call() -> list[dict]:
    call = {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}}
    return [
        {"role": "user", "content": "leggi a.py"},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": "print(1)"},
        {"role": "assistant", "content": "fatto"},
    ]


def test_snapshot_conserva_le_tool_call(state: SessionState) -> None:
    """L'istantanea JSON mantiene cio' che il .txt perdeva: tool_calls e tool_call_id."""
    state.messages.extend(_storia_con_tool_call())
    snapshot = json.loads(json.dumps(session_snapshot(state), ensure_ascii=False))
    assert snapshot["modello"] == state.model.id
    tool_call = next(m for m in snapshot["messaggi"] if m.get("tool_calls"))
    assert tool_call["tool_calls"][0]["id"] == "c1"
    risultato = next(m for m in snapshot["messaggi"] if m.get("role") == "tool")
    assert risultato["tool_call_id"] == "c1"
    assert validate_snapshot(snapshot) is None


def test_snapshot_non_valido_viene_respinto() -> None:
    """Un salvataggio manomesso produce un errore leggibile, non una storia rotta."""
    assert validate_snapshot("non un oggetto") is not None
    assert validate_snapshot({"messaggi": []}) is not None
    assert validate_snapshot({"messaggi": [{"role": "marziano", "content": "x"}]}) is not None
    orfano = {"messaggi": [{"role": "tool", "tool_call_id": "mai-chiamato", "content": "x"}]}
    assert "senza la chiamata" in (validate_snapshot(orfano) or "")


# ---------------------------------------------------------------------------
# riassunto LLM
# ---------------------------------------------------------------------------


def _client_finto(testo: str | None = None, boom: bool = False) -> SimpleNamespace:
    def create(**kwargs: object) -> SimpleNamespace:
        if boom:
            raise RuntimeError("provider giu'")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=testo))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_riassunto_llm_usato_quando_disponibile() -> None:
    """Con un summarizer funzionante il contenuto compattato e' quello del modello."""
    messages: list[dict] = []
    for i in range(8):
        call = {"id": f"c{i}", "function": {"name": "read_file", "arguments": "{}"}}
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "name": "read_file", "content": "dato\n" * 200})
    compattati, _ = compact_tool_results(messages, summarizer=lambda content, name: "Letto il file: 3 funzioni.")
    assert compattati > 0
    primo = next(m for m in messages if m.get("role") == "tool")
    assert "Letto il file: 3 funzioni." in primo["content"]
    assert primo["content"].startswith(COMPACT_PREFIX)


def test_riassunto_llm_fallisce_e_si_ricade_sul_deterministico() -> None:
    """Se il modello non risponde, la compattazione avviene comunque."""
    assert summarize_with_llm(_client_finto(boom=True), "m", "contenuto", "read_file") is None
    assert summarize_with_llm(_client_finto(testo=""), "m", "contenuto", "read_file") is None
    assert summarize_with_llm(_client_finto(testo="ok"), "m", "contenuto", "read_file") == "ok"
