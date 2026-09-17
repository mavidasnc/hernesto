"""Test per lo strumento run_command: troncamento, denylist, dry-run, interruzione."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ernesto.config import DEFAULT_DENY_PATTERNS, STDERR_OUTPUT_LIMIT, TOOL_OUTPUT_LIMIT
from ernesto.session import SessionState
from ernesto.tools import LEVEL_DESTRUCTIVE, LEVEL_WARNING, ConfirmFn
from ernesto.tools.shell import RunCommandTool, find_deny_match, find_escaping_path


def _make_tool(
    state: SessionState,
    confirm_fn: ConfirmFn | None = None,
) -> RunCommandTool:
    return RunCommandTool(state, confirm_fn or (lambda message, preview=None, level='': False))


def _proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    """Processo finto: communicate() restituisce la coppia (stdout, stderr)."""
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
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


def test_output_non_decodificabile(state: SessionState) -> None:
    """Un byte non decodificabile nella codifica locale non fa sparire l'output.

    Regressione: con text=True senza encoding la decodifica avveniva in cp1252 dentro il
    thread lettore di communicate(), l'eccezione non risaliva e il tool restituiva
    "exit 0" con output vuoto.
    """
    command = 'python -c "import sys; sys.stdout.buffer.write(bytes([0x41, 0x9d, 0x42]))"'
    result = _make_tool(state).run(command=command)
    assert result.startswith("exit 0")
    assert "A" in result and "B" in result
    assert "�" in result  # il byte illeggibile diventa il carattere di sostituzione


def test_stdin_non_ereditato(state: SessionState) -> None:
    """Un comando che legge stdin fallisce subito invece di restare appeso al timeout."""
    result = _make_tool(state).run(command='python -c "input()"', timeout=20)
    assert not result.startswith("exit 0")
    assert "EOF" in result


@patch("ernesto.tools.shell.subprocess.Popen")
def test_stdout_e_stderr_separati(mock_popen: MagicMock, state: SessionState) -> None:
    """Con entrambi gli stream presenti l'output e' etichettato."""
    mock_popen.return_value = _proc(stdout="risultato", stderr="attenzione")
    result = _make_tool(state).run(command="npm test")
    assert "--- stdout ---" in result
    assert "--- stderr ---" in result
    assert result.index("risultato") < result.index("attenzione")


@patch("ernesto.tools.shell.subprocess.Popen")
def test_stderr_troncato_separatamente(mock_popen: MagicMock, state: SessionState) -> None:
    """Uno stderr enorme non mangia lo stdout: i due stream hanno tetti indipendenti."""
    mock_popen.return_value = _proc(stdout="segnale", stderr="x" * (STDERR_OUTPUT_LIMIT * 5))
    result = _make_tool(state).run(command="pip install qualcosa")
    assert "segnale" in result
    assert "troncato" in result
    assert len(result) < TOOL_OUTPUT_LIMIT


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
    tool = _make_tool(state, confirm_fn=lambda message, preview=None, level='': True)
    result = tool.run(command="sudo ls")
    assert result.startswith("exit 0")
    mock_popen.assert_called_once()


@patch("ernesto.tools.shell.subprocess.Popen")
def test_denylist_skipped_with_yolo(mock_popen: MagicMock, state: SessionState) -> None:
    """Con yolo attivo la conferma non viene mai chiesta."""
    mock_popen.return_value = _proc(stdout="ok")
    state.yolo = True
    calls: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = '') -> bool:
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


def test_guardia_path_assoluto_chiede_conferma(state: SessionState) -> None:
    """run_command non e' sandboxato: un percorso assoluto passa dalla conferma."""
    with patch("ernesto.tools.shell.subprocess.Popen") as mock_popen:
        result = _make_tool(state).run(command=r"curl -o C:\Windows\preso.txt https://e.com")
    assert result.startswith("ERRORE")
    assert "fuori dalla cartella di lavoro" in result
    mock_popen.assert_not_called()


@patch("ernesto.tools.shell.subprocess.Popen")
def test_guardia_path_relativo_dentro_workdir_non_scatta(mock_popen: MagicMock, state: SessionState) -> None:
    """I comandi normali con percorsi relativi non vengono disturbati."""
    mock_popen.return_value = _proc(stdout="ok")
    result = _make_tool(state).run(command="python -m pytest tests/test_shell.py -q")
    assert result.startswith("exit 0")


@patch("ernesto.tools.shell.subprocess.Popen")
def test_guardia_saltata_con_yolo(mock_popen: MagicMock, state: SessionState) -> None:
    """Con yolo la guardia non chiede nulla, come le altre conferme."""
    mock_popen.return_value = _proc(stdout="ok")
    state.yolo = True
    result = _make_tool(state).run(command="cat /etc/passwd")
    assert result.startswith("exit 0")


def test_guardia_riconosce_i_frammenti_attesi() -> None:
    """Path assoluti e risalite vengono intercettati, i percorsi relativi no."""
    assert find_escaping_path("type C:/Users/tizio/segreti.txt") is not None
    assert find_escaping_path("cat /etc/passwd") is not None
    assert find_escaping_path("cp dati.csv ../fuori/") is not None
    assert find_escaping_path("pytest tests/ -q") is None
    assert find_escaping_path("npm run build") is None


def test_denylist_varianti_di_forma() -> None:
    """Le varianti che prima sfuggivano ora vengono intercettate."""
    for comando in (
        "rm -r -f build",
        "rm --recursive --force build",
        "RM -RF build",
        "rm  -rf   build",
        "rm -fr build",
        "git -C . push origin main",
        "GIT PUSH",
    ):
        assert find_deny_match(comando, DEFAULT_DENY_PATTERNS) is not None, comando


def test_denylist_nessun_falso_positivo() -> None:
    """I comandi innocui restano fuori dalla denylist."""
    for comando in (
        "pytest -q",
        "npm run build",
        "git status",
        "git log --oneline -5",
        "python -c \"print('rm')\"",
        "grep -rf pattern.txt src/",  # -rf di grep: legge i pattern da file, non cancella
    ):
        assert find_deny_match(comando, DEFAULT_DENY_PATTERNS) is None, comando


def test_livelli_di_conferma_passati_al_callback(state: SessionState) -> None:
    """Denylist e guardia sui percorsi arrivano con livelli di gravita' diversi."""
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return False

    tool = _make_tool(state, confirm_fn=confirm)
    tool.run(command="rm -rf build")
    tool.run(command="cat /etc/passwd")
    assert livelli == [LEVEL_DESTRUCTIVE, LEVEL_WARNING]
