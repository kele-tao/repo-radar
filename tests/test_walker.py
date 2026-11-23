"""File walking, line counting and bounded reads."""

from __future__ import annotations

from pathlib import Path

from repo_radar.walker import WalkOptions, count_lines, iter_files, load_text
from tests.conftest import write


def test_iter_files_is_sorted_and_relative(tmp_path: Path) -> None:
    write(tmp_path, "b.py", "x = 1\n")
    write(tmp_path, "a.py", "y = 2\n")
    write(tmp_path, "nested/c.py", "z = 3\n")
    files = iter_files(tmp_path)
    assert [f.rel for f in files] == ["a.py", "b.py", "nested/c.py"]


def test_iter_files_skips_ignored_and_binary(tmp_path: Path) -> None:
    write(tmp_path, "keep.py", "x = 1\n")
    write(tmp_path, "node_modules/pkg/index.js", "var a = 1;\n")
    write(tmp_path, "logo.png", "not really a png")
    rels = [f.rel for f in iter_files(tmp_path)]
    assert rels == ["keep.py"]


def test_ignore_option_filters_patterns(tmp_path: Path) -> None:
    write(tmp_path, "keep.py", "x = 1\n")
    write(tmp_path, "vendor/lib.py", "y = 2\n")
    files = iter_files(tmp_path, WalkOptions(ignore=("vendor",)))
    assert [f.rel for f in files] == ["keep.py"]


def test_gitignore_in_root_is_honoured(tmp_path: Path) -> None:
    write(tmp_path, ".gitignore", "generated/\n*.log\n")
    write(tmp_path, "app.py", "x = 1\n")
    write(tmp_path, "generated/schema.py", "y = 2\n")
    write(tmp_path, "run.log", "noise\n")
    assert [f.rel for f in iter_files(tmp_path)] == [".gitignore", "app.py"]


def test_large_file_is_marked_not_read(tmp_path: Path) -> None:
    write(tmp_path, "big.py", "x = 1\n" * 100)
    files = iter_files(tmp_path, WalkOptions(max_file_bytes=10))
    assert files[0].skipped_reason == "too-large"
    assert load_text(files[0]) == ""


def test_binary_content_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "blob.dat"
    path.write_bytes(b"\x00\x01\x02source-looking-name")
    files = iter_files(tmp_path)
    assert files[0].rel == "blob.dat"
    assert load_text(files[0]) == ""
    assert files[0].skipped_reason == "binary"


def test_count_lines_separates_code_comments_blanks(tmp_path: Path) -> None:
    write(tmp_path, "m.py", '"""Doc."""\n\n# comment\nx = 1\ny = 2\n')
    info = iter_files(tmp_path)[0]
    text = load_text(info)
    count_lines(text, info)
    assert info.lines == 5
    assert info.comments == 2
    assert info.blanks == 1
    assert info.code == 2


def test_count_lines_handles_block_comments(tmp_path: Path) -> None:
    write(tmp_path, "m.js", "/* start\nstill comment\nend */\nlet x = 1;\n")
    info = iter_files(tmp_path)[0]
    text = load_text(info)
    count_lines(text, info)
    assert info.comments == 3
    assert info.code == 1
