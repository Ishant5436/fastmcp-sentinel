#!/usr/bin/env python3
"""Standalone 1-Second Live Demonstration Script for FastMCP-Sentinel."""

import sys
from fastmcp_sentinel.cli import run_demo


def main() -> int:
    ok = run_demo()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
