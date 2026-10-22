"""Unified Command Line Interface for FastMCP-Sentinel.

Subcommands:
- serve: Run the FastMCP stdio server for LLM agent integration.
- check: Run comprehensive local diagnostic checks (C++ core, cache, simulator, audit).
- demo: Execute a 1-second standalone live demonstration of all 5 security subsystems.
- audit: Run the Power of 10 static audit and exit non-zero on violations.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import List

from fastmcp_sentinel import __version__

_ARCH = platform.machine() or "native"


def _setup_logging(level: str | None = None) -> None:
    # Always log to stderr: stdout carries the MCP stdio protocol.
    logging.basicConfig(
        level=(level or os.environ.get("SENTINEL_LOG_LEVEL", "INFO")).upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run_health_check() -> bool:
    """Execute subsystem diagnostic checks and report status."""
    from fastmcp_sentinel.audit import SafetyInvariantAuditor
    from fastmcp_sentinel.bridge import get_bridge
    from fastmcp_sentinel.guard import GuardConfig, StatefulAgentGuard
    from fastmcp_sentinel.paths import find_csrc_dir
    from fastmcp_sentinel.simulation import EvmSimulator

    print("=" * 70)
    print("  FASTMCP-SENTINEL: SYSTEM DIAGNOSTIC HEALTH CHECK")
    print("=" * 70)
    all_ok = True

    # 1. C++ Engine & Arena
    t0 = time.perf_counter_ns()
    try:
        bridge = get_bridge()
        stats = bridge.cache_stats()
        latency_us = (time.perf_counter_ns() - t0) / 1000.0
        print(f"  [PASS] C++ Invariant Core ({_ARCH}) : Arena ready ({stats['capacity']} slots, {latency_us:.1f} µs)")
    except Exception as e:
        print(f"  [FAIL] C++ Invariant Core ({_ARCH}) : {e}")
        print("-" * 70)
        print("  OVERALL STATUS: DIAGNOSTICS FAILED (native core unavailable)")
        print("=" * 70)
        return False

    # 2. Kernel Validation Latency
    try:
        t0 = time.perf_counter_ns()
        v_res = bridge.validate_transaction(
            to_address="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            value_eth=0.5,
            gas_limit=100000,
            calldata_hex="0xa9059cbb00000000000000000000000011111111111111111111111111111111111111110000000000000000000000000000000000000000000000000000000000000001",
        )
        latency_us = (time.perf_counter_ns() - t0) / 1000.0
        if not v_res.is_valid:
            raise RuntimeError(v_res.reason)
        print(f"  [PASS] Calldata Validation Gate    : Selector {v_res.function_selector} ({latency_us:.1f} µs)")
    except Exception as e:
        print(f"  [FAIL] Calldata Validation Gate    : {e}")
        all_ok = False

    # 3. Ring Buffer Cache
    try:
        bridge.cache_put("health:ping", "pong")
        if bridge.cache_get("health:ping") != "pong":
            raise RuntimeError("read-back mismatch")
        print("  [PASS] Ring-Buffer Cache           : Slot write/read verified")
    except Exception as e:
        print(f"  [FAIL] Ring-Buffer Cache           : {e}")
        all_ok = False

    # 4. EVM Zero-Mutation Simulator (offline mock backend)
    try:
        sim = EvmSimulator(rpc_url="mock://local")
        s_res = sim.simulate_call(
            to="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            data="0x70a082310000000000000000000000001111111111111111111111111111111111111111",
        )
        if not s_res.success:
            raise RuntimeError(s_res.revert_reason)
        print(f"  [PASS] Simulation Engine (mock)    : Simulation passed (gas: {s_res.gas_used})")
    except Exception as e:
        print(f"  [FAIL] Simulation Engine (mock)    : {e}")
        all_ok = False

    # 5. Financial Spend Guard
    try:
        guard = StatefulAgentGuard(GuardConfig(max_session_spend_wei=10**18))
        chk = guard.check_transaction("0x1111111111111111111111111111111111111111", value_wei=5 * 10**17)
        if not chk.allowed:
            raise RuntimeError(chk.reason)
        print("  [PASS] Stateful Agent Spend Guard  : Token-bucket & spend sandbox operational")
    except Exception as e:
        print(f"  [FAIL] Stateful Agent Spend Guard  : {e}")
        all_ok = False

    # 6. Holzmann Power of 10 Audit
    try:
        report = SafetyInvariantAuditor(find_csrc_dir()).audit()
        if not report.passed:
            raise RuntimeError("; ".join(report.violations))
        print(f"  [PASS] Holzmann Power of 10 Audit  : {len(report.function_metrics)} functions, 0 violations")
    except Exception as e:
        print(f"  [FAIL] Holzmann Power of 10 Audit  : {e}")
        all_ok = False

    print("-" * 70)
    status_label = "100% HEALTHY - READY FOR AGENT DEPLOYMENT" if all_ok else "DIAGNOSTICS FAILED"
    print(f"  OVERALL STATUS: {status_label}")
    print("=" * 70)
    return all_ok


def run_demo() -> bool:
    """Run an end-to-end 1-second demonstration of all security gates."""
    from fastmcp_sentinel.audit import SafetyInvariantAuditor
    from fastmcp_sentinel.bridge import get_bridge
    from fastmcp_sentinel.guard import GuardConfig, StatefulAgentGuard
    from fastmcp_sentinel.paths import find_csrc_dir
    from fastmcp_sentinel.simulation import EvmSimulator

    t_start = time.perf_counter()
    print("=" * 70)
    print("  FASTMCP-SENTINEL: LIVE DEMONSTRATION")
    print("=" * 70)

    bridge = get_bridge()
    sim = EvmSimulator(rpc_url="mock://local")
    guard = StatefulAgentGuard(
        GuardConfig(
            max_single_tx_wei=10**18,  # 1 ETH
            max_session_spend_wei=2 * 10**18,  # 2 ETH
        )
    )
    ok = True

    # Demo Step 1: Sub-millisecond C++ Calldata Validation
    print("\n[Step 1] Sub-millisecond Native Calldata Validation:")
    calldata_hex = "a9059cbb000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa960450000000000000000000000000000000000000000000000000de0b6b3a7640000"
    res1 = bridge.validate_transaction(
        to_address="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        value_eth=0.1,
        gas_limit=50000,
        calldata_hex=calldata_hex,
    )
    ok &= res1.is_valid
    print(f"  -> Selector Decoded : {res1.function_selector} (ERC20 transfer)")
    print(f"  -> Invariant Status : {res1.status_name} ({res1.reason})")
    print(f"  -> Execution Latency: {res1.latency_us:.2f} µs (zero-copy {_ARCH} C++)")

    # Demo Step 2: C++ Invariant Enforcement on Dangerous Tx
    print("\n[Step 2] Blocking Value Overflow (> 100 ETH Ceiling):")
    res_bad = bridge.validate_transaction(
        to_address="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        value_eth=150.0,
        gas_limit=50000,
    )
    ok &= not res_bad.is_valid
    print(f"  -> Transaction Valid: {res_bad.is_valid}")
    print(f"  -> Rejection Code   : {res_bad.status_name} ({res_bad.status_code})")
    print(f"  -> Rejection Reason : {res_bad.reason}")

    # Demo Step 3: Zero-Mutation State Fork Simulation
    print("\n[Step 3] Pre-Flight EVM Simulation (Catching Reverts, mock backend):")
    sim_revert = sim.simulate_call(
        to="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        data="0xa9059cbb_mock_revert_slippage_exceeded",
    )
    ok &= not sim_revert.success
    print(f"  -> Simulation Success: {sim_revert.success}")
    print(f"  -> Decoded Revert    : {sim_revert.revert_reason}")

    # Demo Step 4: Stateful Spend Guard Budget Limiter
    print("\n[Step 4] Stateful Agent Spend Guard (Preventing Loss):")
    recipient = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    tx1 = guard.authorize(recipient, value_wei=10**18, tx_ref="0xhash1")
    print(
        f"  -> Tx 1 (1.0 ETH): Allowed = {tx1.allowed} (Remaining: {tx1.remaining_session_budget_wei / 10**18:.1f} ETH)"
    )
    tx2 = guard.authorize(recipient, value_wei=15 * 10**17)
    print(f"  -> Tx 2 (1.5 ETH): Allowed = {tx2.allowed} ({tx2.reason})")
    ok &= tx1.allowed and not tx2.allowed

    # Demo Step 5: Power of 10 Safety Audit
    print("\n[Step 5] Power of 10 Static Compliance Audit:")
    report = SafetyInvariantAuditor(find_csrc_dir()).audit()
    ok &= report.passed
    max_lines = max((f.line_count for f in report.function_metrics), default=0)
    print(
        f"  -> Audit Result       : {'PASS' if report.passed else 'FAIL'} "
        f"({len(report.function_metrics)} C++ functions, {len(report.violations)} violations)"
    )
    print(f"  -> Max Function Lines : {max_lines} (Holzmann Rule 4 limit: 60)")

    elapsed = time.perf_counter() - t_start
    print("\n" + "=" * 70)
    verdict = "COMPLETED SUCCESSFULLY" if ok else "FAILED"
    print(f"  DEMONSTRATION {verdict} IN {elapsed * 1000:.0f} ms")
    print("=" * 70)
    return bool(ok)


def run_audit(csrc_dir: str | None, as_json: bool) -> bool:
    from fastmcp_sentinel.audit import SafetyInvariantAuditor
    from fastmcp_sentinel.paths import find_csrc_dir

    directory = Path(csrc_dir) if csrc_dir else find_csrc_dir()
    report = SafetyInvariantAuditor(directory).audit()
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return report.passed

    print("=" * 65)
    print("  FASTMCP-SENTINEL: POWER OF 10 SAFETY INVARIANTS AUDIT")
    print("=" * 65)
    for rule_name, passed in report.rules_checked.items():
        print(f"  {'[PASS]' if passed else '[FAIL]'} {rule_name}")
    print("-" * 65)
    print(f"  Functions Audited : {len(report.function_metrics)}")
    for f in report.function_metrics:
        print(f"    - {f.name:<25} ({f.file}): {f.line_count:2d} lines, {f.assert_count} asserts")
    print("-" * 65)
    if report.passed:
        print("  RESULT: 100% COMPLIANT - ALL SAFETY INVARIANTS SATISFIED")
    else:
        print(f"  RESULT: FAILED WITH {len(report.violations)} VIOLATIONS:")
        for v in report.violations:
            print(f"    ! {v}")
    print("=" * 65)
    return report.passed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fastmcp-sentinel",
        description="FastMCP-Sentinel: Deterministic Safety & RPC Gateway for Autonomous AI Agents",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--log-level", default=None, help="Log level (default: $SENTINEL_LOG_LEVEL or INFO)")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    subparsers.add_parser("serve", help="Start FastMCP stdio server")
    subparsers.add_parser("check", help="Run diagnostic health checks")
    subparsers.add_parser("demo", help="Run 1-second live demo")
    audit = subparsers.add_parser("audit", help="Run the Power of 10 static audit")
    audit.add_argument("--csrc-dir", default=None, help="Directory of C++ sources to audit")
    audit.add_argument("--json", action="store_true", help="Emit the report as JSON")
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    # The server logs guard decisions at INFO; interactive commands stay quiet by default.
    _setup_logging(
        args.log_level or os.environ.get("SENTINEL_LOG_LEVEL") or ("INFO" if args.command == "serve" else "WARNING")
    )

    if args.command == "serve":
        from fastmcp_sentinel import server

        settings = server.configure()
        logging.getLogger("fastmcp_sentinel").info(
            "starting stdio server version=%s allow_custom_rpc=%s allow_mock_rpc=%s allow_agent_reset=%s",
            __version__,
            settings.allow_custom_rpc,
            settings.allow_mock_rpc,
            settings.allow_agent_reset,
        )
        server.mcp.run(transport="stdio")
    elif args.command == "check":
        sys.exit(0 if run_health_check() else 1)
    elif args.command == "demo":
        sys.exit(0 if run_demo() else 1)
    elif args.command == "audit":
        sys.exit(0 if run_audit(args.csrc_dir, args.json) else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
