"""Terminal renderer and the self-contained HTML dashboard."""

from __future__ import annotations

import re
from pathlib import Path

from repo_radar.htmlreport import build_html
from repo_radar.render import render_explain, render_scan
from repo_radar.scan import collect
from repo_radar.utils import Style, bar, display_width, human_size, pad, truncate
from tests.conftest import write


def test_render_scan_colourless_has_no_escape_codes(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    text = render_scan(result, colour=False)
    assert "\x1b[" not in text
    assert "REPO HEALTH" in text


def test_render_scan_with_colour_emits_ansi(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    text = render_scan(result, colour=True)
    assert "\x1b[" in text


def test_render_explain_lists_symbols(clean_repo: Path) -> None:
    from repo_radar.explain import explain_file

    exp = explain_file(clean_repo / "src/demo/math.py", clean_repo)
    text = render_explain(exp, colour=False)
    assert "PUBLIC API" in text
    assert "add" in text


def test_html_is_self_contained(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    html = build_html(result, top=5)
    assert html.startswith("<!doctype html>")
    assert "<svg" in html
    assert "<style>" in html
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "https://" not in html or "github.com/kele-tao" in html


def test_html_contains_measured_numbers(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    html = build_html(result)
    assert "%d" % result.total_files in html
    assert "GRADE " + result.grade in html


def test_html_escapes_untrusted_names(tmp_path: Path) -> None:
    write(tmp_path, "evil.py", "eval(payload)\n")
    write(tmp_path, "a&b.py", "eval(payload)\n")
    result = collect(tmp_path, with_git=False)
    html = build_html(result)
    assert "a&amp;b.py" in html
    assert "a&b.py" not in html


def test_html_is_deterministic_for_the_same_scan(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    first = build_html(result, top=3)
    second = build_html(result, top=3)
    first_body = re.sub(r"<footer>.*</footer>", "", first, flags=re.S)
    second_body = re.sub(r"<footer>.*</footer>", "", second, flags=re.S)
    assert first_body == second_body


def test_bar_and_human_size_helpers() -> None:
    assert bar(0, 10) == "\u2591" * 10
    assert bar(100, 10) == "\u2588" * 10
    assert human_size(2048) == "2.0 KB"
    assert human_size(999) == "999 B"


def test_display_width_handles_cjk() -> None:
    assert display_width("abc") == 3
    assert display_width("中文") == 4
    assert pad("中文", 6) == "中文  "
    assert truncate("abcdef", 4).endswith("…")


def test_style_disabled_is_plain_text() -> None:
    style = Style(False)
    assert style.red("x") == "x"
    assert style.bold("x") == "x"
    enabled = Style(True)
    assert "\x1b[" in enabled.red("x")
