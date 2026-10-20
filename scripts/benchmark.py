#!/usr/bin/env python3
"""Reproducible latency benchmark for FastMCP-Sentinel's hot paths.

Reports warm median and p99 latency in microseconds. Run with: python scripts/benchmark.py
"""

import platform
import time

from fastmcp_sentinel.bridge import get_bridge
from fastmcp_sentinel.guard import StatefulAgentGuard, GuardConfig

ITERATIONS = 20000
WARMUP = 500
TO_ADDRESS = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
CALLDATA_HEX = "0xa9059cbb" + "00" * 12 + "d8" * 20 + f"{10**18:064x}"


def bench(fn):
    for _ in range(WARMUP):
        fn()
    samples = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    return samples[len(samples) // 2] / 1000.0, samples[int(len(samples) * 0.99)] / 1000.0


def main() -> None:
    bridge = get_bridge()
    raw_calldata = bytes.fromhex(CALLDATA_HEX[2:])
    bridge.cache_put("eth_chainId:[]", "0x13b2")
    guard = StatefulAgentGuard(
        GuardConfig(max_session_spend_wei=10**30, burst_limit=10**9, rate_limit_per_minute=10**9)
    )

    cases = [
        ("C++ validate_tx (ctypes call only)", lambda: bridge.validate_tx(TO_ADDRESS, raw_calldata, 10**17, 50000)),
        ("validate_transaction (hex parse + C++)", lambda: bridge.validate_transaction(TO_ADDRESS, 0.1, 50000, CALLDATA_HEX)),
        ("C++ ring cache get (hit)", lambda: bridge.cache_get("eth_chainId:[]")),
        ("Spend guard check (Python)", lambda: guard.check_transaction(TO_ADDRESS, 1)),
    ]

    print(f"Platform: {platform.system()} {platform.machine()} / Python {platform.python_version()}")
    print(f"{'Subsystem':<42} {'median µs':>10} {'p99 µs':>10}")
    for name, fn in cases:
        median, p99 = bench(fn)
        print(f"{name:<42} {median:>10.2f} {p99:>10.2f}")


if __name__ == "__main__":
    main()
