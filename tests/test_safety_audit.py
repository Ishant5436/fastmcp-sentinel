import pytest
import tempfile
from pathlib import Path
from fastmcp_sentinel.audit import SafetyInvariantAuditor

def test_audit_passes_on_real_csrc():
    repo_root = Path(__file__).resolve().parent.parent
    csrc_dir = repo_root / "csrc"
    auditor = SafetyInvariantAuditor(csrc_dir)
    report = auditor.audit()

    assert report.passed is True
    assert len(report.violations) == 0
    assert len(report.function_metrics) >= 6
    assert all(report.rules_checked.values())

def test_audit_flags_violations_on_synthetic_code():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        bad_cpp = tmp_path / "bad.cpp"
        bad_cpp.write_text("""
#include <cstdlib>

void bad_function() {
    int* p = (int*)malloc(sizeof(int));
    goto finish;
finish:
    free(p);
}
""", encoding="utf-8")

        auditor = SafetyInvariantAuditor(tmp_path)
        report = auditor.audit()

        assert report.passed is False
        assert len(report.violations) > 0
        violations_str = " ".join(report.violations)
        assert "Rule 1 Violation" in violations_str  # goto
        assert "Rule 3 Violation" in violations_str  # malloc/free
        assert "Rule 5 Violation" in violations_str  # < 2 asserts
