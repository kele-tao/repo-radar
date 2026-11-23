"""Configuration precedence: CLI > environment > .radar.yml > .radarignore."""

from __future__ import annotations

from pathlib import Path

from repo_radar.config import Config, load_config
from tests.conftest import write


def test_empty_repository_has_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.ignore == ()
    assert config.fail_under is None
    assert config.top == 10
    assert config.warnings == []


def test_radarignore_is_read(tmp_path: Path) -> None:
    write(tmp_path, ".radarignore", "# comment\nnode_modules\n*.min.js\n")
    config = load_config(tmp_path)
    assert config.ignore == ("node_modules", "*.min.js")
    assert ".radarignore" in config.sources


def test_yaml_config_sets_fail_under_and_top(tmp_path: Path) -> None:
    write(tmp_path, ".radar.yml", "fail_under: 72.5\ntop: 4\nignore: [dist]\n")
    config = load_config(tmp_path)
    assert config.fail_under == 72.5
    assert config.top == 4
    assert "dist" in config.ignore


def test_cli_beats_config_file(tmp_path: Path) -> None:
    write(tmp_path, ".radar.yml", "fail_under: 99\n")
    config = load_config(tmp_path, fail_under=10.0)
    assert config.fail_under == 10.0
    assert "cli" in config.sources


def test_environment_beats_config_file(tmp_path: Path, monkeypatch) -> None:
    write(tmp_path, ".radar.yml", "fail_under: 99\n")
    monkeypatch.setenv("REPO_RADAR_FAIL_UNDER", "42")
    monkeypatch.setenv("REPO_RADAR_IGNORE", "build,vendor")
    config = load_config(tmp_path)
    assert config.fail_under == 42.0
    assert "build" in config.ignore
    assert "vendor" in config.ignore


def test_bad_yaml_produces_warning(tmp_path: Path) -> None:
    write(tmp_path, ".radar.yml", "nonsense line\n")
    config = load_config(tmp_path)
    assert config.warnings
    assert "line 1" in config.warnings[0]


def test_bad_environment_number_produces_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPO_RADAR_FAIL_UNDER", "not-a-number")
    config = load_config(tmp_path)
    assert config.fail_under is None
    assert config.warnings


def test_config_is_serialisable(tmp_path: Path) -> None:
    config = load_config(tmp_path, ignore=("x",), fail_under=50.0)
    payload = config.as_dict()
    assert payload["ignore"] == ["x"]
    assert payload["fail_under"] == 50.0
    assert isinstance(config, Config)
