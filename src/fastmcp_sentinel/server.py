"""FastMCP Sentinel Server.

Deterministic Agentic Safety & RPC Gateway exposing 6 native FastMCP tools:
1. sentinel_validate_calldata: C++ calldata bounds validation & selector decoding.
2. sentinel_simulate_transaction: Read-only eth_call / eth_estimateGas simulation & revert decoding.
3. sentinel_rpc_cache: Fixed-size C++ ring-buffer cache (FIFO eviction, optional TTL) for RPC payloads.
4. sentinel_agent_guard: Stateful session USDC spend caps, reservations and rate limiting.
5. sentinel_audit_invariants: Static AST verification of Holzmann's Power of 10 invariants.
6. sentinel_preflight: Single gate running validate -> simulate -> reserve before broadcast.
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
    ARC_MAX_SINGLE_TX_NATIVE,
    ARC_MAX_SESSION_SPEND_NATIVE,
    native_to_usdc,
    usdc_exposure_native,
)

# Initialize FastMCP Server
mcp = FastMCP("fastmcp-sentinel")

# Shared Engine Singletons
_bridge = get_bridge()
_simulator = EvmSimulator()
_guard = StatefulAgentGuard(
    GuardConfig(
        max_single_tx_wei=ARC_MAX_SINGLE_TX_NATIVE,  # 10 USDC (18-decimal native units)
        max_session_spend_wei=ARC_MAX_SESSION_SPEND_NATIVE,  # 50 USDC
        rate_limit_per_minute=60,
        burst_limit=10,
    )
)

_CSRC_DIR = Path(__file__).resolve().parent.parent.parent / "csrc"


@mcp.tool()
def sentinel_validate_calldata(
    to_address: str,
    value_native: float = 0.0,
    gas_limit: int = 100000,
    calldata_hex: str = "0x",
    value_eth: float | None = None,
) -> Dict[str, Any]:
    """Validate EVM transaction parameters and calldata via the native C++ core.

    Enforces 32KB bounded buffer limits, a 100 native-unit value ceiling (100 USDC on Arc),
    a 15M gas ceiling, and decodes the 4-byte function selector.
    `value_native` is in whole native units; `value_eth` is a deprecated alias.
    """
    if value_eth is not None:
        value_native = value_eth
    if value_native < 0:
        return {"is_valid": False, "status_name": "ERR_NEGATIVE_VALUE", "reason": "Value cannot be negative"}
    res = _bridge.validate_transaction(
        to_address=to_address,
        value_native=value_native,
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
    gas: int = 0,
    rpc_url: str = "",
) -> Dict[str, Any]:
    """Simulate transaction execution against latest chain state without mutation.

    Runs eth_call and eth_estimateGas, returning success, decoded revert reason, estimated gas
    and return data before an agent signs or broadcasts. `gas` = 0 lets the node estimate.
    Defaults to Arc Mainnet when `rpc_url` is empty.
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
    max_age_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Manage the fixed-size C++ ring-buffer cache for static RPC reads.

    Actions:
    - 'get': Retrieve cached payload by key; entries older than `max_age_seconds` are
      treated as misses (0 = never expire).
    - 'put': Store or overwrite a payload in the fixed 1024-slot arena (oldest entry evicted).
    - 'stats': Return capacity, count, and memory arena initialization status.
    """
    act = action.strip().lower()
    if act == "get":
        val = _bridge.cache_get(key, max_age_ns=int(max(0.0, max_age_seconds) * 1e9))
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
    calldata_hex: str = "0x",
    reservation_id: str = "",
) -> Dict[str, Any]:
    """Enforce session-wide USDC spend limits, address filtering, and rate limits.

    Spend is measured in 18-decimal native USDC units and includes ERC-20 transfer/approve
    amounts sent to the Arc USDC interface (pass `calldata_hex` for those).

    Actions:
    - 'check': Advisory check of a planned transaction (nothing is held).
    - 'reserve': Check and hold the amount against the budget; returns `reservation_id`.
    - 'confirm': Finalize a reservation after broadcast (`reservation_id`, `tx_hash`).
    - 'release': Refund a reservation whose transaction was never broadcast.
    - 'record': Record an executed transaction directly to update cumulative spend.
    - 'status' / 'arc_status': Query spend, reservations, budget and rate limit tokens.
    - 'reset': Reset the active session spend accumulator.
    """
    act = action.strip().lower()
    if act in ("check", "reserve"):
        if value_wei < 0:
            return {"allowed": False, "status_name": "INVALID_VALUE", "reason": "value_wei cannot be negative"}
        exposure = usdc_exposure_native(to_address, value_wei, calldata_hex)
        if act == "check":
            return _guard.check_transaction(target_address=to_address, value_wei=exposure).to_dict()
        res, rid = _guard.reserve_transaction(target_address=to_address, value_wei=exposure)
        out = res.to_dict()
        out["reservation_id"] = rid
        out["usdc_exposure"] = native_to_usdc(exposure) if exposure < 2**255 else None
        return out
    elif act == "confirm":
        ok = _guard.confirm_reservation(reservation_id, tx_hash)
        return {"status": "confirmed" if ok else "unknown_reservation", "reservation_id": reservation_id}
    elif act == "release":
        ok = _guard.release_reservation(reservation_id)
        return {"status": "released" if ok else "unknown_reservation", "reservation_id": reservation_id}
    elif act == "record":
        try:
            _guard.record_transaction(tx_hash=tx_hash, value_wei=value_wei)
        except ValueError as err:
            return {"status": "rejected", "reason": str(err)}
        return {"status": "recorded", "tx_hash": tx_hash, "value_wei": value_wei}
    elif act == "status":
        return _guard.get_status()
    elif act == "arc_status":
        status = _guard.get_status()
        status["network"] = "Arc Mainnet"
        status["chain_id"] = ARC_CHAIN_ID
        status["gas_asset"] = ARC_GAS_TOKEN
        status["session_spend_usdc"] = native_to_usdc(status["session_spend_wei"])
        status["reserved_usdc"] = native_to_usdc(status["reserved_wei"])
        status["remaining_session_budget_usdc"] = native_to_usdc(status["remaining_session_budget_wei"])
        status["max_session_spend_usdc"] = native_to_usdc(status["max_session_spend_wei"])
        status["max_single_tx_usdc"] = native_to_usdc(status["max_single_tx_wei"])
        return status
    elif act == "reset":
        _guard.reset_session()
        return {"status": "reset"}
    else:
        return {
            "error": f"Unknown guard action '{action}'. Valid actions: 'check', 'reserve', "
            "'confirm', 'release', 'record', 'status', 'arc_status', 'reset'"
        }


@mcp.tool()
def sentinel_audit_invariants() -> Dict[str, Any]:
    """Execute static AST analysis verifying Power of 10 Safety Invariants on C++ core.

    Audits maximum function lengths (<= 60 lines), assertion densities (>= 2 asserts/func),
    absence of dynamic heap allocation (malloc/new/free), and bounded control flows.
    """
    auditor = SafetyInvariantAuditor(_CSRC_DIR)
    report = auditor.audit()
    return report.to_dict()


@mcp.tool()
def sentinel_preflight(
    to_address: str,
    from_address: str = "0x0000000000000000000000000000000000000000",
    value_wei: int = 0,
    data: str = "0x",
    gas: int = 0,
    rpc_url: str = "",
) -> Dict[str, Any]:
    """Run every gate before an agent signs: C++ validation, simulation, then a spend reservation.

    Stops at the first failing stage. Only when all stages pass is the USDC amount reserved
    against the session budget and a `reservation_id` returned. After broadcasting, call
    sentinel_agent_guard(action='confirm', reservation_id=..., tx_hash=...); if the transaction
    is abandoned, call action='release'.
    """
    stages: Dict[str, Any] = {}
    if value_wei < 0:
        return {"approved": False, "failed_stage": "validate", "reason": "value_wei cannot be negative", "stages": stages}

    validation = _bridge.validate_transaction(
        to_address=to_address,
        value_wei=value_wei,
        gas_limit=gas if gas > 0 else 100000,
        calldata_hex=data,
    )
    stages["validate"] = validation.to_dict()
    if not validation.is_valid:
        return {"approved": False, "failed_stage": "validate", "reason": validation.reason, "stages": stages}

    sim = sentinel_simulate_transaction(
        to_address=to_address,
        from_address=from_address,
        value_wei=value_wei,
        data=data,
        gas=gas,
        rpc_url=rpc_url,
    )
    stages["simulate"] = sim
    if not sim["success"]:
        return {"approved": False, "failed_stage": "simulate", "reason": sim["revert_reason"], "stages": stages}

    guard = sentinel_agent_guard(action="reserve", to_address=to_address, value_wei=value_wei, calldata_hex=data)
    stages["guard"] = guard
    if not guard["allowed"]:
        return {"approved": False, "failed_stage": "guard", "reason": guard["reason"], "stages": stages}

    return {
        "approved": True,
        "reservation_id": guard["reservation_id"],
        "usdc_exposure": guard["usdc_exposure"],
        "stages": stages,
    }


def main() -> None:
    """Run FastMCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
