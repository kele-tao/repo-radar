"""Risk rules: each rule fires on the planted pattern and stays quiet otherwise."""

from __future__ import annotations

from repo_radar.findings import (
    RULES,
    Rule,
    rule_frequency,
    scan_python_ast,
    scan_text,
    severity_counts,
)


def rules_of(findings) -> set[str]:
    return {f.rule for f in findings}


def test_rule_catalogue_is_consistent() -> None:
    assert len(RULES) >= 20
    for rule in RULES.values():
        assert isinstance(rule, Rule)
        assert rule.severity in {"high", "medium", "low", "info"}
        assert rule.title and rule.fix


def test_hardcoded_credential_is_high_severity() -> None:
    findings = scan_text("app.py", 'API_KEY = "sk_live_9f8e7d6c5b4a3210"\n', "Python")
    assert "RR001" in rules_of(findings)
    assert all(f.severity == "high" for f in findings if f.rule == "RR001")


def test_placeholder_secret_is_not_flagged() -> None:
    findings = scan_text("settings.py", 'password = "changeme-in-example"\n', "Python")
    assert "RR001" not in rules_of(findings)


def test_dynamic_execution_rules() -> None:
    findings = scan_text("run.py", "result = eval(payload)\n", "Python")
    assert "RR002" in rules_of(findings)


def test_shell_injection_rule() -> None:
    findings = scan_text("deploy.py", "subprocess.run(cmd, shell=True)\n", "Python")
    assert "RR004" in rules_of(findings)


def test_tls_verification_rule() -> None:
    findings = scan_text("client.py", "requests.get(url, verify=False)\n", "Python")
    assert "RR005" in rules_of(findings)


def test_yaml_loader_rule() -> None:
    findings = scan_text("conf.py", "data = yaml.load(stream)\n", "Python")
    assert "RR006" in rules_of(findings)


def test_ast_rules_for_assert_and_bare_except() -> None:
    source = (
        "def check(x):\n"
        "    assert x, 'must be set'\n"
        "\n"
        "def swallow():\n"
        "    try:\n"
        "        return 1\n"
        "    except:\n"
        "        pass\n"
    )
    findings = scan_python_ast("mod.py", source)
    found = rules_of(findings)
    assert "RR007" in found
    assert "RR008" in found


def test_assert_is_allowed_in_tests() -> None:
    source = "def test_x():\n    assert 1 == 1\n"
    assert "RR007" not in rules_of(scan_python_ast("tests/test_x.py", source))


def test_mutable_default_argument() -> None:
    source = "def collect(items=[]):\n    items.append(1)\n    return items\n"
    assert "RR009" in rules_of(scan_python_ast("mod.py", source))


def test_wildcard_import() -> None:
    assert "RR010" in rules_of(scan_python_ast("mod.py", "from os.path import *\n"))


def test_marker_rule_respects_tests() -> None:
    text = "# TO" + "DO: rewrite this\n"
    assert "RR013" in rules_of(scan_text("src/mod.py", text, "Python"))
    assert "RR013" not in rules_of(scan_text("tests/test_mod.py", text, "Python"))


def test_print_rule_skips_scripts_and_tests() -> None:
    text = 'print("hello")\n'
    assert "RR020" in rules_of(scan_text("src/library.py", text, "Python"))
    assert "RR020" not in rules_of(scan_text("scripts/tool.py", text, "Python"))
    assert "RR020" not in rules_of(scan_text("src/cli.py", text, "Python"))


def test_severity_counts_and_rule_frequency_are_deterministic() -> None:
    findings = scan_text("app.py", 'eval(x)\npassword = "abcdef123456"\n', "Python")
    counts = severity_counts(findings)
    assert counts["high"] >= 2
    first = rule_frequency(findings)
    second = rule_frequency(list(reversed(findings)))
    assert first == second
    assert first[0][1] >= 1


def test_invalid_python_does_not_raise() -> None:
    assert scan_python_ast("broken.py", "def (:\n") == []


def test_unicode_and_emoji_input_is_safe() -> None:
    text = "# 注释 with emoji ✨ and CJK" + chr(10) + 'password = "abcd1234efgh"' + chr(10)
    findings = scan_text("mod.py", text, "Python")
    assert "RR001" in rules_of(findings)
