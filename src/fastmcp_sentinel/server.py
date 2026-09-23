"""FastMCP Sentinel Server.

Deterministic Agentic Safety & RPC Gateway exposing 5 native FastMCP tools:
1. sentinel_validate_calldata: Zero-copy C++ calldata validation & heuristic checks.
2. sentinel_simulate_transaction: Zero-mutation EVM state simulation & revert decoding.
3. sentinel_rpc_cache: High-throughput C++ LRU ring-buffer cache for RPC payloads.
4. sentinel_agent_guard: Stateful session spend caps and rate limiting.
5. sentinel_audit_invariants: Static AST verification of Holzmann's Power of 10 invariants.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP

from fastmcp_sentinel.bridge import get_bridge
from fastmcp_sentinel.simulation import EvmSimulator
from fastmcp_sentinel.guard import StatefulAgentGuard, GuardConfig
from fastmcp_sentinel.audit import SafetyInvariantAuditor
from fastmcp_sentinel.config import (
    ARC_CHAIN_ID,
    ARC_RPC_URL,
    ARC_GAS_TOKEN,
    base_units_to_usdc,
)

# Initialize FastMCP Server
mcp = FastMCP("fastmcp-sentinel")

# Shared Engine Singletons
_bridge = get_bridge()
_simulator = EvmSimulator()
_guard = StatefulAgentGuard(
    GuardConfig(
        max_single_tx_wei=10**18,  # 1 ETH
        max_session_spend_wei=5 * 10**18,  # 5 ETH
        rate_limit_per_minute=60,
        burst_limit=10,
    )
)

_CSRC_DIR = Path(__file__).resolve().parent.parent.parent / "csrc"


@mcp.tool()
def sentinel_validate_calldata(
    to_address: str,
    value_eth: float = 0.0,
    gas_limit: int = 100000,
    calldata_hex: str = "0x",
) -> Dict[str, Any]:
    """Validate EVM transaction parameters and calldata via Apple Silicon C++ core.

    Enforces 32KB bounded buffer limits, value ceiling (< 100 ETH), gas ceiling (< 15M gas),
    and decodes the 4-byte function selector with sub-millisecond zero-copy latency.
    """
    res = _bridge.validate_transaction(
        to_address=to_address,
        value_eth=value_eth,
        gas_limit=gas_limit,
        calldata_hex=calldata_hex,
    )
    return res.to_dict()


@mcp.tool()
def sentinel_simulate_transaction(
    to_address: str,
    from_address: str = "0x0000000000000000000000000000000000000000",
    value_wei: int = 0,
    data: str = "0x",
    gas: int = 21000,
    rpc_url: str = "",
) -> Dict[str, Any]:
    """Simulate transaction execution against an EVM JSON-RPC state fork without mutation.

    Returns execution success, decoded revert reason, exact gas consumed, and return data
    before allowing an agent to sign or broadcast.
    """
    target_rpc = rpc_url.strip() if rpc_url.strip() else ARC_RPC_URL
    sim = _simulator.simulate(
        to_address=to_address,
        from_address=from_address,
        value_wei=value_wei,
        data=data,
        gas=gas,
        rpc_url=target_rpc,
    )
    res = sim.to_dict()
    res["target_rpc"] = target_rpc
    res["chain_id"] = ARC_CHAIN_ID if target_rpc == ARC_RPC_URL else None
    return res


@mcp.tool()
def sentinel_rpc_cache(
    action: str,
    key: str = "",
    value: str = "",
) -> Dict[str, Any]:
    """Manage high-performance C++ ring-buffer LRU cache for static RPC reads.

    Actions:
    - 'get': Retrieve cached JSON payload by key.
    - 'put': Store payload in fixed 1024-slot circular arena.
    - 'stats': Return capacity, count, and memory arena initialization status.
    """
    act = action.strip().lower()
    if act == "get":
        val = _bridge.cache_get(key)
        found = val is not None
        code = 0 if found else -7
        return {"action": "get", "key": key, "value": val or "", "status_code": code, "found": found}
    elif act == "put":
        ok = _bridge.cache_put(key, value)
        code = 0 if ok else -6
        return {"action": "put", "key": key, "status_code": code, "stored": ok}
    elif act == "stats":
        stats = _bridge.cache_stats()
        stats["action"] = "stats"
        return stats
    else:
        return {"error": f"Unknown cache action '{action}'. Valid actions: 'get', 'put', 'stats'"}


@mcp.tool()
def sentinel_agent_guard(
    action: str,
    to_address: str = "",
    value_wei: int = 0,
    tx_hash: str = "",
) -> Dict[str, Any]:
    """Enforce session-wide financial spend limits, address filtering, and rate limits.

    Actions:
    - 'check': Validate if a planned transaction is within session budget and rate limits.
    - 'record': Record an executed transaction to update cumulative spend.
    - 'status': Query current session spend, remaining budget, and rate limit tokens.
    - 'reset': Reset the active session spend accumulator.
    """
    act = action.strip().lower()
    if act == "check":
        res = _guard.check_transaction(target_address=to_address, value_wei=value_wei)
        return res.to_dict()
    elif act == "record":
        _guard.record_transaction(tx_hash=tx_hash, value_wei=value_wei)
        return {"status": "recorded", "tx_hash": tx_hash, "value_wei": value_wei}
    elif act == "status":
        return _guard.get_status()
    elif act == "arc_status":
        status = _guard.get_status()
        status["network"] = "Arc Mainnet"
        status["chain_id"] = ARC_CHAIN_ID
        status["gas_asset"] = ARC_GAS_TOKEN
        status["session_spend_usdc"] = base_units_to_usdc(status.get("session_spend_wei", 0))
        status["remaining_session_budget_usdc"] = base_units_to_usdc(status.get("remaining_session_budget_wei", 0))
        return status
    elif act == "reset":
        _guard.reset_session()
        return {"status": "reset"}
    else:
        return {"error": f"Unknown guard action '{action}'. Valid actions: 'check', 'record', 'status', 'arc_status', 'reset'"}


@mcp.tool()
def sentinel_audit_invariants() -> Dict[str, Any]:
    """Execute static AST analysis verifying Power of 10 Safety Invariants on C++ core.

    Audits maximum function lengths (<= 60 lines), assertion densities (>= 2 asserts/func),
    absence of dynamic heap allocation (malloc/new/free), and bounded control flows.
    """
    auditor = SafetyInvariantAuditor(_CSRC_DIR)
    report = auditor.audit()
    return report.to_dict()


def main() -> None:
    """Run FastMCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
