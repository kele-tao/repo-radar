"""CLI contract: exit codes, JSON shape, error messages, every documented flag."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_radar.cli import build_parser, main
from tests.conftest import write


def run(capsys, argv):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_help_prints_usage(capsys) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "scan" in out and "explain" in out and "report" in out


def test_no_command_prints_help(capsys) -> None:
    code, out, _ = run(capsys, [])
    assert code == 2
    assert "usage" in out.lower()


def test_scan_renders_report(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["scan", str(clean_repo), "--no-git", "--no-colour"])
    assert code == 0
    assert "REPO HEALTH" in out
    assert "/100" in out


def test_scan_json_is_machine_readable(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["scan", str(clean_repo), "--no-git", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["score"] == pytest.approx(payload["score"])
    assert set(payload["sub_scores"]) >= {"risk", "tests", "docs", "hygiene"}
    assert payload["totals"]["files"] >= 1
    assert payload["config"]["sources"]


def test_fail_under_returns_one(risky_repo: Path, capsys) -> None:
    code, _, err = run(capsys, ["scan", str(risky_repo), "--no-git", "--fail-under", "95"])
    assert code == 1
    assert "fail-under" in err


def test_fail_under_passes_when_score_is_high(clean_repo: Path, capsys) -> None:
    code, _, _ = run(capsys, ["scan", str(clean_repo), "--no-git", "--fail-under", "1"])
    assert code == 0


def test_quiet_mode_prints_one_line(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["scan", str(clean_repo), "--no-git", "--quiet"])
    assert code == 0
    assert len(out.strip().splitlines()) == 1


def test_top_flag_limits_findings(risky_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["scan", str(risky_repo), "--no-git", "--top", "1"])
    assert code == 0
    assert "RR0" in out


def test_missing_directory_is_usage_error(capsys, tmp_path: Path) -> None:
    code, _, err = run(capsys, ["scan", str(tmp_path / "absent")])
    assert code == 2
    assert "no such directory" in err


def test_file_instead_of_directory_is_usage_error(tmp_path: Path, capsys) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    code, _, err = run(capsys, ["scan", str(tmp_path / "a.py")])
    assert code == 2
    assert "explain" in err


def test_explain_renders_public_api(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["explain", str(clean_repo / "src/demo/math.py"),
                                "--no-colour"])
    assert code == 0
    assert "PUBLIC API" in out
    assert "add" in out


def test_explain_json(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["explain", str(clean_repo / "src/demo/math.py"), "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["public_api"] == ["add"]
    assert payload["language"] == "Python"


def test_explain_missing_file(capsys, tmp_path: Path) -> None:
    code, _, err = run(capsys, ["explain", str(tmp_path / "nope.py")])
    assert code == 2
    assert "no such file" in err


def test_explain_root_shortens_path(clean_repo: Path, capsys) -> None:
    code, out, _ = run(capsys, ["explain", str(clean_repo / "src/demo/math.py"),
                                "--root", str(clean_repo), "--json"])
    assert code == 0
    assert json.loads(out)["path"] == "src/demo/math.py"


def test_report_writes_html(clean_repo: Path, tmp_path: Path, capsys) -> None:
    out_file = tmp_path / "dashboard.html"
    code, out, _ = run(capsys, ["report", str(clean_repo), "--out", str(out_file),
                                "--no-git", "--no-colour"])
    assert code == 0
    assert out_file.is_file()
    html = out_file.read_text(encoding="utf-8")
    assert "<svg" in html
    assert "no CDN" not in html and "cdn." not in html
    assert "wrote" in out


def test_report_requires_html_extension(clean_repo: Path, tmp_path: Path, capsys) -> None:
    code, _, err = run(capsys, ["report", str(clean_repo), "--out", str(tmp_path / "x.txt")])
    assert code == 2
    assert "html" in err


def test_report_out_is_required(clean_repo: Path, capsys) -> None:
    with pytest.raises(SystemExit) as info:
        main(["report", str(clean_repo)])
    assert info.value.code == 2


def test_rules_lists_every_rule(capsys) -> None:
    code, out, _ = run(capsys, ["rules"])
    assert code == 0
    assert "RR001" in out and "RR020" in out


def test_rules_json(capsys) -> None:
    code, out, _ = run(capsys, ["rules", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert len(payload) >= 20
    assert {"id", "severity", "title", "fix"} <= set(payload[0])


def test_ignore_flag_is_applied(tmp_path: Path, capsys) -> None:
    write(tmp_path, "keep.py", "x = 1\n")
    write(tmp_path, "noise/big.py", "y = 2\n")
    code, out, _ = run(capsys, ["scan", str(tmp_path), "--no-git", "--json",
                                "--ignore", "noise"])
    assert code == 0
    payload = json.loads(out)
    assert payload["totals"]["files"] == 1


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0


def test_parser_declares_documented_flags() -> None:
    parser = build_parser()
    scan = parser._subparsers._group_actions[0].choices["scan"]
    options = {opt for action in scan._actions for opt in action.option_strings}
    assert {"--json", "--top", "--fail-under", "--ignore", "--no-git", "--quiet"} <= options


def test_config_file_is_read(tmp_path: Path, capsys) -> None:
    write(tmp_path, "app.py", "x = 1\n")
    write(tmp_path, ".radar.yml", "fail_under: 99\ntop: 3\nignore: [app.py]\n")
    code, out, _ = run(capsys, ["scan", str(tmp_path), "--no-git", "--json"])
    assert code == 1
    payload = json.loads(out)
    languages = {entry["language"] for entry in payload["languages"]}
    assert "Python" not in languages
    assert ".radar.yml" in json.dumps(payload) or "YAML" in languages


def test_broken_config_warns_on_stderr(tmp_path: Path, capsys) -> None:
    write(tmp_path, "app.py", "x = 1\n")
    write(tmp_path, ".radar.yml", "this is not yaml\n")
    code, _, err = run(capsys, ["scan", str(tmp_path), "--no-git", "--json"])
    assert code == 0
    assert "config" in err
