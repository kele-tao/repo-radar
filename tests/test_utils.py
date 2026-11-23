"""Small helpers that the renderer and CLI depend on."""

from __future__ import annotations

import pathlib

from repo_radar.utils import (
    Style,
    color_enabled,
    human_int,
    human_size,
    pct,
    plural,
    read_text,
    strip_ansi,
    write_text,
)


def test_color_enabled_honours_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert color_enabled() is False


def test_color_enabled_honours_force_color(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert color_enabled() is True


def test_color_enabled_without_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    class Plain:
        def isatty(self) -> bool:
            return False

    assert color_enabled(Plain()) is False


def test_strip_ansi_removes_sequences() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"


def test_human_size_and_int() -> None:
    assert human_size(0) == "0 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_int(1234567) == "1,234,567"


def test_pct_and_plural() -> None:
    assert pct(1, 4) == 25.0
    assert pct(1, 0) == 0.0
    assert plural(1, "file") == "1 file"
    assert plural(3, "file") == "3 files"
    assert plural(2, "match", "matches") == "2 matches"


def test_grade_colouring() -> None:
    style = Style(True)
    assert "\x1b[32m" in style.grade(95)
    assert "\x1b[33m" in style.grade(65)
    assert "\x1b[31m" in style.grade(10)


def test_read_text_handles_bom_and_latin1(tmp_path: pathlib.Path) -> None:
    bom = tmp_path / "bom.txt"
    bom.write_bytes(b"\xef\xbb\xbfhello")
    assert read_text(bom) == "hello"
    latin = tmp_path / "latin.txt"
    latin.write_bytes("caf\xe9".encode("latin-1"))
    assert "caf" in read_text(latin)


def test_write_text_is_utf8_and_creates_parents(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "deep/nested/out.txt"
    write_text(target, "unicode ✨\n")
    assert target.read_text(encoding="utf-8") == "unicode ✨\n"
