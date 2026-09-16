"""Test per il log JSONL: masking dei segreti e troncamento."""

from __future__ import annotations

import json
from pathlib import Path

from ernesto.session import SessionLogger, fmt_tokens, mask_secret

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
