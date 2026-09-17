#!/usr/bin/env python3
"""CLI runner for Holzmann Power of 10 Safety Invariants Audit.

Exits with code 0 if all rules pass, or 1 if violations are detected.
"""

import sys
from pathlib import Path
from fastmcp_sentinel.audit import SafetyInvariantAuditor


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    csrc_dir = repo_root / "csrc"

    auditor = SafetyInvariantAuditor(csrc_dir)
    report = auditor.audit()

    print("=" * 65)
    print("  FASTMCP-SENTINEL: POWER OF 10 SAFETY INVARIANTS AUDIT")
    print("=" * 65)

    for rule_name, passed in report.rules_checked.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {rule_name}")

    print("-" * 65)
    print(f"  Functions Audited : {len(report.function_metrics)}")
    for f in report.function_metrics:
        print(f"    - {f.name:<25} ({f.file}): {f.line_count:2d} lines, {f.assert_count} asserts")

    print("-" * 65)
    if report.passed:
        print("  RESULT: 100% COMPLIANT - ALL SAFETY INVARIANTS SATISFIED")
        print("=" * 65)
        return 0
    else:
        print(f"  RESULT: FAILED WITH {len(report.violations)} VIOLATIONS:")
        for v in report.violations:
            print(f"    ! {v}")
        print("=" * 65)
        return 1


if __name__ == "__main__":
    sys.exit(main())
