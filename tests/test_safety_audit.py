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
        bad_cpp.write_text(
            """
#include <cstdlib>

void bad_function() {
    int* p = (int*)malloc(sizeof(int));
    goto finish;
finish:
    free(p);
}
""",
            encoding="utf-8",
        )

        auditor = SafetyInvariantAuditor(tmp_path)
        report = auditor.audit()

        assert report.passed is False
        assert len(report.violations) > 0
        violations_str = " ".join(report.violations)
        assert "Rule 1 Violation" in violations_str  # goto
        assert "Rule 3 Violation" in violations_str  # malloc/free
        assert "Rule 5 Violation" in violations_str  # < 2 asserts


def test_audit_ignores_comments_and_strings(tmp_path):
    (tmp_path / "ok.cpp").write_text(
        """
/** Allocate a new entry -- docs mentioning malloc and free and goto. */
int f(int x) {
    assert(x >= 0);
    assert(x < 10);
    const char* msg = "delete this { brace";  // new comment
    return msg[0] + x;
}
""",
        encoding="utf-8",
    )
    report = SafetyInvariantAuditor(tmp_path).audit()
    assert report.passed, report.violations
    assert [f.name for f in report.function_metrics] == ["f"]


def test_audit_flags_recursion(tmp_path):
    (tmp_path / "rec.cpp").write_text(
        """
int fact(int n) {
    assert(n >= 0);
    assert(n < 20);
    return n == 0 ? 1 : n * fact(n - 1);
}
""",
        encoding="utf-8",
    )
    report = SafetyInvariantAuditor(tmp_path).audit()
    assert not report.passed
    assert any("recursive" in v for v in report.violations)
