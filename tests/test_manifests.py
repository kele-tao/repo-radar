"""Manifest detection: ecosystems, entry points, tests, CI and dependency pinning."""

from __future__ import annotations

from pathlib import Path

from repo_radar.manifests import detect, entry_point_score
from tests.conftest import write


def test_python_pyproject_is_parsed(clean_repo: Path) -> None:
    eco = detect(clean_repo, [p.relative_to(clean_repo).as_posix()
                              for p in clean_repo.rglob("*") if p.is_file()])
    manifests = {m.kind: m for m in eco.manifests}
    assert "pyproject.toml" in manifests
    assert manifests["pyproject.toml"].dependencies == ["requests"]
    assert "Python (pyproject)" in eco.ecosystems
    assert eco.dependency_pinned == 1


def test_requirements_file_is_parsed(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt",
          "# pinned\nrequests==2.31.0\nflask>=2.0\n--index-url https://example.invalid\n")
    eco = detect(tmp_path, ["requirements.txt"])
    manifest = eco.manifests[0]
    assert manifest.dependencies == ["requests", "flask"]
    assert manifest.pinned == 2
    assert "Python (requirements)" in eco.ecosystems


def test_node_manifest_and_lockfile(tmp_path: Path) -> None:
    write(tmp_path, "package.json",
          '{"name": "app", "main": "index.js", "dependencies": {"react": "18.2.0"},'
          ' "devDependencies": {"vitest": "^1.0.0"}, "scripts": {"start": "node ."}}')
    write(tmp_path, "package-lock.json", "{}")
    eco = detect(tmp_path, ["package.json", "package-lock.json"])
    manifest = eco.manifests[0]
    assert manifest.dependencies == ["react"]
    assert manifest.dev_dependencies == ["vitest"]
    assert manifest.pinned == 1
    assert eco.has_lockfile
    assert "Node" in eco.ecosystems
    assert any(entry == "main = index.js" for _, entry in eco.entry_points)


def test_malformed_package_json_is_ignored(tmp_path: Path) -> None:
    write(tmp_path, "package.json", "{not json")
    eco = detect(tmp_path, ["package.json"])
    assert eco.manifests == []


def test_go_module_and_main(tmp_path: Path) -> None:
    write(tmp_path, "go.mod", "module example.com/x\n\ngo 1.22\n\nrequire (\n"
                              "\tgithub.com/spf13/cobra v1.8.0\n)\n")
    write(tmp_path, "main.go", "package main\n\nfunc main() {}\n")
    eco = detect(tmp_path, ["go.mod", "main.go"])
    assert "Go" in eco.ecosystems
    assert ("main.go", "go main package") in eco.entry_points
    assert eco.dependency_total >= 1


def test_cargo_manifest(tmp_path: Path) -> None:
    write(tmp_path, "Cargo.toml", '[package]\nname = "x"\n[dependencies]\nserde = "1"\n')
    write(tmp_path, "src/main.rs", "fn main() {}\n")
    eco = detect(tmp_path, ["Cargo.toml", "src/main.rs"])
    assert "Rust" in eco.ecosystems
    assert eco.manifests[0].dependencies == ["serde"]
    assert ("src/main.rs", "rust binary") in eco.entry_points


def test_docker_make_and_ci_are_detected(tmp_path: Path) -> None:
    for name in ("Dockerfile", "Makefile", ".github/workflows/ci.yml",
                 ".pre-commit-config.yaml", "LICENSE", "README.md"):
        write(tmp_path, name, "x\n")
    eco = detect(tmp_path, ["Dockerfile", "Makefile", ".github/workflows/ci.yml",
                            ".pre-commit-config.yaml", "LICENSE", "README.md"])
    assert eco.has_docker
    assert eco.has_ci
    assert eco.has_pre_commit
    assert eco.has_readme and eco.has_license
    assert "GitHub Actions" in eco.ci_systems


def test_gitlab_and_circleci(tmp_path: Path) -> None:
    write(tmp_path, ".gitlab-ci.yml", "stages: []\n")
    write(tmp_path, ".circleci/config.yml", "version: 2\n")
    eco = detect(tmp_path, [".gitlab-ci.yml", ".circleci/config.yml"])
    assert "GitLab CI" in eco.ci_systems
    assert "CircleCI" in eco.ci_systems


def test_test_framework_detection(tmp_path: Path) -> None:
    write(tmp_path, "conftest.py", "import pytest\n")
    write(tmp_path, "tests/test_a.py", "def test_a():\n    pass\n")
    eco = detect(tmp_path, ["conftest.py", "tests/test_a.py"])
    assert "pytest" in eco.test_frameworks
    assert eco.has_tests_dir


def test_jest_is_detected_from_config(tmp_path: Path) -> None:
    write(tmp_path, "jest.config.js", "module.exports = {}\n")
    write(tmp_path, "src/a.test.js", "test('x', () => {});\n")
    eco = detect(tmp_path, ["jest.config.js", "src/a.test.js"])
    assert "jest" in eco.test_frameworks


def test_pin_ratio_and_serialisation(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "a==1\nb==2\nc\n")
    eco = detect(tmp_path, ["requirements.txt"])
    assert eco.pin_ratio == 66.7
    payload = eco.as_dict()
    assert payload["dependencies"] == 3
    assert payload["pinned_dependencies"] == 2


def test_entry_point_score_bands(tmp_path: Path) -> None:
    empty = detect(tmp_path, [])
    assert entry_point_score(empty) == 30.0
    write(tmp_path, "pyproject.toml", '[project]\nname = "x"\n'
                                      '[project.scripts]\nx = "x.cli:main"\n')
    write(tmp_path, "Dockerfile", "FROM scratch\n")
    rich = detect(tmp_path, ["pyproject.toml", "Dockerfile"])
    assert entry_point_score(rich) > entry_point_score(empty)


def test_manifest_inside_subdirectory_is_located(tmp_path: Path) -> None:
    write(tmp_path, "web/package.json", '{"name": "web", "dependencies": {"preact": "^10"}}')
    eco = detect(tmp_path, ["web/package.json"])
    assert eco.manifests[0].path == "web/package.json"
