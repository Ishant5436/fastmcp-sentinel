#!/usr/bin/env python3
"""CLI runner for Holzmann Power of 10 Safety Invariants Audit.

Exits with code 0 if all rules pass, or 1 if violations are detected.
Equivalent to ``fastmcp-sentinel audit --csrc-dir csrc``.
"""

import sys
from pathlib import Path

from fastmcp_sentinel.cli import run_audit


def main() -> int:
    csrc_dir = Path(__file__).resolve().parent.parent / "csrc"
    return 0 if run_audit(str(csrc_dir), as_json="--json" in sys.argv[1:]) else 1


if __name__ == "__main__":
    sys.exit(main())
