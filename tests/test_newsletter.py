"""Test per newsletter_query: subprocess mockato, nessun DB reale."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from ernesto.session import SessionState
from ernesto.tools import LEVEL_WARNING
from ernesto.tools.newsletter import FULL_CONTENT_CHARS, NewsletterQueryTool


class FakeProc:
    """Risultato finto di subprocess.run."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Finto progetto newsletter con lo script di interrogazione."""
    proj = tmp_path / "newsletter"
    proj.mkdir()
    (proj / "query_articles.py").write_text("# finto script", encoding="utf-8")
    return proj


@pytest.fixture
def configured_state(state: SessionState, project: Path) -> SessionState:
    """SessionState con newsletter.dir che punta al progetto finto."""
    context_dir = state.workdir / "context"
    context_dir.mkdir(exist_ok=True)
    (context_dir / "config.yaml").write_text(f"newsletter:\n  dir: {project}\n", encoding="utf-8")
    return state


def _confirm_si(message: str, preview: str | None = None, level: str = "") -> bool:
    return True


def _mock_run(monkeypatch: pytest.MonkeyPatch, proc: FakeProc) -> list[list[str]]:
    """Sostituisce subprocess.run e restituisce la lista degli argv catturati."""
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> FakeProc:
        calls.append(argv)
        return proc

    monkeypatch.setattr("ernesto.tools.newsletter.subprocess.run", fake_run)
    return calls


def test_script_mancante(configured_state: SessionState, tmp_path: Path) -> None:
    """Senza query_articles.py l'errore spiega come configurare il percorso."""
    context_dir = configured_state.workdir / "context"
    (context_dir / "config.yaml").write_text("newsletter:\n  dir: /non/esiste\n", encoding="utf-8")
    result = NewsletterQueryTool(configured_state, _confirm_si).run()
    assert result.startswith("ERRORE")
    assert "newsletter.dir" in result


def test_argv_default(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Di default: processed=0, finestra di 4 giorni, formato JSON."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[]"))
    NewsletterQueryTool(configured_state, _confirm_si).run()
    argv = calls[0]
    assert argv[1].endswith("query_articles.py")
    assert argv[argv.index("--format") + 1] == "json"
    assert "--processed" in argv and argv[argv.index("--processed") + 1] == "0"
    assert argv[argv.index("--since") + 1] == (date.today() - timedelta(days=4)).isoformat()
    assert argv[argv.index("--until") + 1] == date.today().isoformat()
    assert "--full-content" not in argv


def test_formato_table(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """La panoramica compatta passa --format table e l'output non viene toccato."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[  688] 2026-09-18 | Fonte | titolo\n"))
    result = NewsletterQueryTool(configured_state, _confirm_si).run(format="table")
    assert calls[0][calls[0].index("--format") + 1] == "table"
    assert result.startswith("[  688]")


def test_ids_sostituiscono_le_date(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Con ids la selezione e' puntuale: niente filtro temporale."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[]"))
    NewsletterQueryTool(configured_state, _confirm_si).run(ids="12,34", full_content=True)
    argv = calls[0]
    assert argv[argv.index("--ids") + 1] == "12,34"
    assert "--since" not in argv and "--until" not in argv
    assert "--full-content" in argv


def test_days_personalizzati(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Il parametro days sposta la finestra."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[]"))
    NewsletterQueryTool(configured_state, _confirm_si).run(days=7, source="openai")
    argv = calls[0]
    assert argv[argv.index("--since") + 1] == (date.today() - timedelta(days=7)).isoformat()
    assert argv[argv.index("--source") + 1] == "openai"


def test_count_only(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """count_only passa --count e restituisce il numero."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="42\n"))
    result = NewsletterQueryTool(configured_state, _confirm_si).run(count_only=True)
    assert "--count" in calls[0]
    assert result == "42"


def test_full_content_troncato_per_articolo(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """I contenuti estesi vengono tagliati al tetto per articolo."""
    rows = [{"id": 1, "content_text": "x" * (FULL_CONTENT_CHARS * 2)}]
    _mock_run(monkeypatch, FakeProc(stdout=json.dumps(rows)))
    result = NewsletterQueryTool(configured_state, _confirm_si).run(ids="1", full_content=True)
    text = json.loads(result)[0]["content_text"]
    assert len(text) == FULL_CONTENT_CHARS + 1  # +1 per i puntini


def test_stdout_vuoto_restituisce_stderr(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Zero risultati: lo script scrive su stderr, il tool lo riporta."""
    _mock_run(monkeypatch, FakeProc(stdout="", stderr="Nessun articolo trovato con questi filtri."))
    result = NewsletterQueryTool(configured_state, _confirm_si).run()
    assert "Nessun articolo trovato" in result


def test_exit_nonzero_e_errore(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Un exit code != 0 diventa una stringa ERRORE, mai un'eccezione."""
    _mock_run(monkeypatch, FakeProc(stderr="DB non trovato", returncode=1))
    result = NewsletterQueryTool(configured_state, _confirm_si).run()
    assert result.startswith("ERRORE")
    assert "DB non trovato" in result


def test_subprocess_che_lancia(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Anche un'eccezione del subprocess diventa una stringa ERRORE."""

    def failing_run(*a: object, **k: object) -> FakeProc:
        raise OSError("eseguibile mancante")

    monkeypatch.setattr("ernesto.tools.newsletter.subprocess.run", failing_run)
    result = NewsletterQueryTool(configured_state, _confirm_si).run()
    assert result.startswith("ERRORE")


def test_mark_processed_dry_run(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """In dry-run la marcatura e' simulata e il subprocess non parte."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[]"))
    configured_state.dry_run = True
    result = NewsletterQueryTool(configured_state, _confirm_si).run(mark_processed=True)
    assert result.startswith("DRY-RUN")
    assert calls == []


def test_mark_processed_senza_conferma(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Senza conferma la marcatura non viene eseguita."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="[]"))
    tool = NewsletterQueryTool(configured_state, lambda message, preview=None, level="": False)
    result = tool.run(mark_processed=True)
    assert "annullata" in result
    assert calls == []


def test_mark_processed_con_conferma(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Con conferma la selezione viene marcata; il livello e' WARNING."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="7", stderr="[mark-processed] 7 articoli marcati."))
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return True

    result = NewsletterQueryTool(configured_state, confirm).run(mark_processed=True)
    assert "--mark-processed" in calls[0]
    assert "--count" in calls[0]  # il LIMIT non deve fermare la marcatura
    assert livelli == [LEVEL_WARNING]
    assert "7 articoli marcati" in result


def test_mark_processed_yolo_salta_la_conferma(monkeypatch: pytest.MonkeyPatch, configured_state: SessionState) -> None:
    """Con yolo la marcatura parte senza conferma interattiva."""
    calls = _mock_run(monkeypatch, FakeProc(stdout="3"))

    def confirm_no(*a: object, **k: object) -> bool:
        raise AssertionError("la conferma non doveva essere chiesta")

    configured_state.yolo = True
    NewsletterQueryTool(configured_state, confirm_no).run(mark_processed=True)
    assert "--mark-processed" in calls[0]
