"""Test per gli strumenti filesystem e la sandbox."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ernesto.session import SessionState
from ernesto.tools.filesystem import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    resolve_in_sandbox,
)


def test_sandbox_path_traversal_parent(state: SessionState, tmp_path: Path) -> None:
    """Un path con ../ che esce dalla workdir viene rifiutato."""
    (tmp_path / "secret.txt").write_text("segreto", encoding="utf-8")
    result = ReadFileTool(state).run(path="../secret.txt")
    assert result == "ERRORE: path fuori dalla sandbox"


def test_sandbox_path_traversal_absolute(state: SessionState, tmp_path: Path) -> None:
    """Un path assoluto fuori dalla workdir viene rifiutato."""
    outside = tmp_path / "secret.txt"
    outside.write_text("segreto", encoding="utf-8")
    result = ReadFileTool(state).run(path=str(outside))
    assert result == "ERRORE: path fuori dalla sandbox"


def test_sandbox_path_traversal_symlink(state: SessionState, tmp_path: Path) -> None:
    """Un symlink dentro la workdir che punta fuori viene rifiutato."""
    outside = tmp_path / "secret.txt"
    outside.write_text("segreto", encoding="utf-8")
    link = state.workdir / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlink non supportati su questa macchina")
    result = ReadFileTool(state).run(path="link.txt")
    assert result == "ERRORE: path fuori dalla sandbox"


def test_resolve_in_sandbox_ok(state: SessionState) -> None:
    """Un path relativo dentro la workdir viene risolto."""
    resolved = resolve_in_sandbox(state.workdir, "sub/file.txt")
    assert resolved is not None
    assert str(resolved).startswith(os.path.realpath(str(state.workdir)))


def test_write_and_read_file(state: SessionState) -> None:
    """write_file crea le directory intermedie e read_file rilegge il contenuto."""
    write = WriteFileTool(state).run(path="sub/dir/hello.txt", content="ciao mondo")
    assert "caratteri scritti" in write
    read = ReadFileTool(state).run(path="sub/dir/hello.txt")
    assert read == "ciao mondo"


def test_read_file_binary_refused(state: SessionState) -> None:
    """Un file binario viene rifiutato con errore leggibile."""
    (state.workdir / "bin.dat").write_bytes(b"\x00\x01\x02")
    result = ReadFileTool(state).run(path="bin.dat")
    assert "binario" in result


def test_edit_file(state: SessionState) -> None:
    """edit_file: sostituzione esatta, errore se non trovata o non univoca."""
    (state.workdir / "f.txt").write_text("aaa bbb aaa", encoding="utf-8")
    edit = EditFileTool(state)
    result = edit.run(path="f.txt", old_string="aaa", new_string="ccc")
    assert "non univoca" in result
    result = edit.run(path="f.txt", old_string="zzz", new_string="ccc")
    assert "non trovata" in result
    result = edit.run(path="f.txt", old_string="bbb", new_string="ccc")
    assert "1 sostituzioni" in result
    assert (state.workdir / "f.txt").read_text(encoding="utf-8") == "aaa ccc aaa"
    result = edit.run(path="f.txt", old_string="aaa", new_string="ddd", replace_all=True)
    assert "2 sostituzioni" in result


def test_list_files(state: SessionState) -> None:
    """list_files elenca file e cartelle con dimensione."""
    (state.workdir / "a.txt").write_text("x", encoding="utf-8")
    (state.workdir / "sub").mkdir()
    result = ListFilesTool(state).run(path=".")
    assert "a.txt" in result
    assert "sub/" in result


def test_list_files_recursive_skips_noise_dirs(state: SessionState) -> None:
    """La ricorsione pota le cartelle generate (.git, .venv, __pycache__, ...)."""
    (state.workdir / "app.py").write_text("x = 1", encoding="utf-8")
    noise = state.workdir / ".venv" / "lib"
    noise.mkdir(parents=True)
    (noise / "junk.py").write_text("pass", encoding="utf-8")
    git = state.workdir / ".git"
    git.mkdir()
    (git / "config").write_text("[core]", encoding="utf-8")
    result = ListFilesTool(state).run(path=".", recursive=True)
    assert "app.py" in result
    assert ".venv" not in result
    assert ".git" not in result


def test_write_file_dry_run(state: SessionState) -> None:
    """In dry-run write_file non tocca il disco."""
    state.dry_run = True
    result = WriteFileTool(state).run(path="nope.txt", content="contenuto")
    assert result.startswith("DRY-RUN")
    assert not (state.workdir / "nope.txt").exists()
