"""Test per lo strumento run_command: troncamento, denylist, dry-run, interruzione."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ernesto.config import DEFAULT_DENY_PATTERNS, TOOL_OUTPUT_LIMIT
from ernesto.session import SessionState
from ernesto.tools import ConfirmFn
from ernesto.tools.shell import RunCommandTool, find_deny_match


def _make_tool(
    state: SessionState,
    confirm_fn: ConfirmFn | None = None,
) -> RunCommandTool:
    return RunCommandTool(state, confirm_fn or (lambda message, preview=None: False))


def _proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Processo finto: communicate() restituisce stdout e nessuno stderr separato."""
    proc = MagicMock()
    proc.communicate.return_value = (stdout, None)
    proc.returncode = returncode
    return proc


@patch("ernesto.tools.shell.subprocess.Popen")
def test_output_truncation(mock_popen: MagicMock, state: SessionState) -> None:
    """L'output oltre 8000 caratteri viene troncato con nota."""
    mock_popen.return_value = _proc(stdout="y" * (TOOL_OUTPUT_LIMIT * 3))
    result = _make_tool(state).run(command="echo hi")
    assert result.startswith("exit 0")
    assert "troncato" in result
    assert len(result) < TOOL_OUTPUT_LIMIT + 200


@patch("ernesto.tools.shell.subprocess.Popen")
def test_denylist_refused_without_confirm(mock_popen: MagicMock, state: SessionState) -> None:
    """Un comando in denylist senza conferma viene rifiutato e non eseguito."""
    result = _make_tool(state).run(command="rm -rf /tmp/prova")
    assert "rifiutato" in result
    mock_popen.assert_not_called()


@patch("ernesto.tools.shell.subprocess.Popen")
def test_denylist_executed_with_confirm(mock_popen: MagicMock, state: SessionState) -> None:
    """Un comando in denylist con conferma positiva viene eseguito."""
    mock_popen.return_value = _proc(stdout="ok")
    tool = _make_tool(state, confirm_fn=lambda message, preview=None: True)
    result = tool.run(command="sudo ls")
    assert result.startswith("exit 0")
    mock_popen.assert_called_once()


@patch("ernesto.tools.shell.subprocess.Popen")
def test_denylist_skipped_with_yolo(mock_popen: MagicMock, state: SessionState) -> None:
    """Con yolo attivo la conferma non viene mai chiesta."""
    mock_popen.return_value = _proc(stdout="ok")
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
    with patch("ernesto.tools.shell.subprocess.Popen") as mock_popen:
        result = _make_tool(state).run(command="echo hi")
    assert result.startswith("DRY-RUN")
    mock_popen.assert_not_called()


@patch("ernesto.tools.shell._kill_tree")
@patch("ernesto.tools.shell.subprocess.Popen")
def test_timeout(mock_popen: MagicMock, mock_kill: MagicMock, state: SessionState) -> None:
    """Un timeout uccide l'albero dei processi e produce un errore leggibile."""
    proc = _proc()
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
    mock_popen.return_value = proc
    result = _make_tool(state).run(command="sleep 99", timeout=1)
    assert "timeout" in result.lower()
    mock_kill.assert_called_once_with(proc)


@patch("ernesto.tools.shell._kill_tree")
@patch("ernesto.tools.shell.subprocess.Popen")
def test_ctrl_c_kills_process_tree(mock_popen: MagicMock, mock_kill: MagicMock, state: SessionState) -> None:
    """Ctrl+C durante il comando: il figlio viene ucciso e l'interruzione risale."""
    proc = _proc()
    proc.communicate.side_effect = KeyboardInterrupt
    mock_popen.return_value = proc
    with pytest.raises(KeyboardInterrupt):
        _make_tool(state).run(command="sleep 99", timeout=60)
    mock_kill.assert_called_once_with(proc)
