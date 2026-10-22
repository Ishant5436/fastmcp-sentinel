import json

import pytest

from fastmcp_sentinel import __version__
from fastmcp_sentinel.cli import main, run_demo, run_health_check


def test_cli_health_check():
    assert run_health_check() is True


def test_cli_run_demo():
    assert run_demo() is True


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_audit_json(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["audit", "--json"])
    assert exc.value.code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is True


def test_cli_audit_fails_on_violations(tmp_path, capsys):
    (tmp_path / "bad.cpp").write_text("void f() { goto x; x: return; }\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["audit", "--csrc-dir", str(tmp_path)])
    assert exc.value.code == 1
    assert "Rule 1 Violation" in capsys.readouterr().out
