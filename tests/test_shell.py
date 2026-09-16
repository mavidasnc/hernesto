"""Test per lo strumento run_command: troncamento, denylist, dry-run."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from ernesto.config import DEFAULT_DENY_PATTERNS, TOOL_OUTPUT_LIMIT
from ernesto.session import SessionState
from ernesto.tools import ConfirmFn
from ernesto.tools.shell import RunCommandTool, find_deny_match


def _make_tool(
    state: SessionState,
    confirm_fn: ConfirmFn | None = None,
) -> RunCommandTool:
    return RunCommandTool(state, confirm_fn or (lambda message, preview=None: False))


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args="cmd", returncode=returncode, stdout=stdout, stderr="")


@patch("ernesto.tools.shell.subprocess.run")
def test_output_truncation(mock_run, state: SessionState) -> None:
    """L'output oltre 8000 caratteri viene troncato con nota."""
    mock_run.return_value = _completed(stdout="y" * (TOOL_OUTPUT_LIMIT * 3))
    result = _make_tool(state).run(command="echo hi")
    assert result.startswith("exit 0")
    assert "troncato" in result
    assert len(result) < TOOL_OUTPUT_LIMIT + 200


@patch("ernesto.tools.shell.subprocess.run")
def test_denylist_refused_without_confirm(mock_run, state: SessionState) -> None:
    """Un comando in denylist senza conferma viene rifiutato e non eseguito."""
    result = _make_tool(state).run(command="rm -rf /tmp/prova")
    assert "rifiutato" in result
    mock_run.assert_not_called()


@patch("ernesto.tools.shell.subprocess.run")
def test_denylist_executed_with_confirm(mock_run, state: SessionState) -> None:
    """Un comando in denylist con conferma positiva viene eseguito."""
    mock_run.return_value = _completed(stdout="ok")
    tool = _make_tool(state, confirm_fn=lambda message, preview=None: True)
    result = tool.run(command="sudo ls")
    assert result.startswith("exit 0")
    mock_run.assert_called_once()


@patch("ernesto.tools.shell.subprocess.run")
def test_denylist_skipped_with_yolo(mock_run, state: SessionState) -> None:
    """Con yolo attivo la conferma non viene mai chiesta."""
    mock_run.return_value = _completed(stdout="ok")
    state.yolo = True
    calls: list[str] = []

    def confirm(message: str, preview: str | None = None) -> bool:
        calls.append(message)
        return False

    result = _make_tool(state, confirm_fn=confirm).run(command="git push origin main")
    assert result.startswith("exit 0")
    assert calls == []


def test_denylist_patterns() -> None:
    """I pattern di default matchano i comandi pericolosi attesi."""
    assert find_deny_match("rm -rf /", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match("sudo apt update", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match("git push origin main", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match("git reset --hard HEAD~1", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match("docker system prune -a", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match(":(){ :|:& };:", DEFAULT_DENY_PATTERNS) is not None
    assert find_deny_match("pytest -q", DEFAULT_DENY_PATTERNS) is None


def test_dry_run(state: SessionState) -> None:
    """In dry-run il comando non viene eseguito."""
    state.dry_run = True
    with patch("ernesto.tools.shell.subprocess.run") as mock_run:
        result = _make_tool(state).run(command="echo hi")
    assert result.startswith("DRY-RUN")
    mock_run.assert_not_called()


@patch("ernesto.tools.shell.subprocess.run")
def test_timeout(mock_run, state: SessionState) -> None:
    """Un timeout produce un errore leggibile."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    result = _make_tool(state).run(command="sleep 99", timeout=1)
    assert "timeout" in result.lower()
