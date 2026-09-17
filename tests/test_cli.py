import pytest
from fastmcp_sentinel.cli import run_health_check, run_demo

def test_cli_health_check():
    success = run_health_check()
    assert success is True

def test_cli_run_demo():
    success = run_demo()
    assert success is True
