"""FastMCP Sentinel Server.

Deterministic Agentic Safety & RPC Gateway exposing 5 native FastMCP tools:
1. sentinel_validate_calldata: Zero-copy C++ calldata validation & heuristic checks.
2. sentinel_simulate_transaction: Zero-mutation EVM state simulation & revert decoding.
3. sentinel_rpc_cache: Fixed-capacity C++ ring-buffer cache (with TTL) for RPC payloads.
4. sentinel_agent_guard: Stateful session spend caps and rate limiting.
5. sentinel_audit_invariants: Static verification of Holzmann's Power of 10 invariants.

Security posture is controlled by :class:`~fastmcp_sentinel.config.SentinelSettings`
(environment variables). Defaults are fail-closed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Literal
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from fastmcp_sentinel.audit import SafetyInvariantAuditor
from fastmcp_sentinel.bridge import SentinelBridge, SentinelStatusCode, get_bridge
from fastmcp_sentinel.config import (
    ARC_CHAIN_ID,
    ARC_GAS_TOKEN,
    SentinelSettings,
    base_units_to_usdc,
)
from fastmcp_sentinel.guard import GuardConfig, StatefulAgentGuard
from fastmcp_sentinel.paths import find_csrc_dir
from fastmcp_sentinel.simulation import EvmSimulator

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
FastMCP-Sentinel is a safety gateway for on-chain actions.
Before signing or broadcasting any transaction:
1. Call `sentinel_validate_calldata` and require `is_valid`.
2. Call `sentinel_simulate_transaction` and require `success`.
3. Call `sentinel_agent_guard` with action `authorize` and require `allowed`
   (this atomically reserves the spend against the session budget).
Use `sentinel_rpc_cache` with a TTL for volatile reads (gasPrice, blockNumber).
"""

mcp = FastMCP("fastmcp-sentinel", instructions=INSTRUCTIONS)


class _ServerState:
    """Lazily-initialized engine singletons, rebuilt by :func:`configure`."""

    def __init__(self, settings: SentinelSettings) -> None:
        self.settings = settings
        self.guard = StatefulAgentGuard(
            GuardConfig(
                max_single_tx_wei=settings.max_single_tx_wei,
                max_session_spend_wei=settings.max_session_spend_wei,
                rate_limit_per_minute=settings.rate_limit_per_minute,
                burst_limit=settings.burst_limit,
                blacklist=set(settings.blocked_addresses),
                whitelist=set(settings.allowed_addresses),
            )
        )
        self._simulators: Dict[str, EvmSimulator] = {}
        self._lock = threading.Lock()

    @property
    def bridge(self) -> SentinelBridge:
        return get_bridge()

    def simulator(self, rpc_url: str) -> EvmSimulator:
        with self._lock:
            sim = self._simulators.get(rpc_url)
            if sim is None:
                sim = EvmSimulator(rpc_url=rpc_url, timeout=self.settings.rpc_timeout_seconds)
                self._simulators[rpc_url] = sim
            return sim


_state: _ServerState | None = None
_state_lock = threading.Lock()


def configure(settings: SentinelSettings | None = None) -> SentinelSettings:
    """(Re)initialize server state. Resets guard session state."""
    global _state
    resolved = settings if settings is not None else SentinelSettings.from_env()
    with _state_lock:
        _state = _ServerState(resolved)
    return resolved


def _get_state() -> _ServerState:
    global _state
    with _state_lock:
        if _state is None:
            _state = _ServerState(SentinelSettings.from_env())
        return _state


def _resolve_rpc(settings: SentinelSettings, rpc_url: str, chain_id: int) -> tuple[str, int | None]:
    """Apply the RPC egress policy. Raises ``ValueError`` when the target is not permitted."""
    by_url = {url: cid for cid, url in settings.rpc_endpoints.items()}
    url = rpc_url.strip()
    if chain_id and url:
        raise ValueError("Pass either rpc_url or chain_id, not both")
    if chain_id:
        if chain_id not in settings.rpc_endpoints:
            raise ValueError(f"Unsupported chain_id {chain_id}; supported: {sorted(settings.rpc_endpoints)}")
        return settings.rpc_endpoints[chain_id], chain_id
    if not url:
        url = settings.default_rpc_url
        return url, by_url.get(url, ARC_CHAIN_ID)
    if url.startswith("mock://"):
        if not settings.allow_mock_rpc:
            raise ValueError("Mock simulation is disabled (set SENTINEL_ALLOW_MOCK_RPC=1 to enable)")
        return url, None
    if url in by_url:
        return url, by_url[url]
    if not settings.allow_custom_rpc:
        raise ValueError("rpc_url is not a configured endpoint; use chain_id or set SENTINEL_ALLOW_CUSTOM_RPC=1")
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("rpc_url must use http or https")
    return url, None


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
def sentinel_validate_calldata(
    to_address: str,
    value_eth: float = 0.0,
    gas_limit: int = 100000,
    calldata_hex: str = "0x",
    value_wei: int | None = None,
) -> Dict[str, Any]:
    """Validate EVM transaction parameters and calldata via the native C++ core.

    Enforces a 0x-prefixed 20-byte target address, 32KB bounded calldata, a well-formed
    4-byte selector, value ceiling (<= 100 ETH), and gas ceiling (<= 15M gas).
    Pass `value_wei` for exact integer amounts; it takes precedence over `value_eth`.
    """
    res = _get_state().bridge.validate_transaction(
        to_address=to_address,
        value_eth=value_eth,
        gas_limit=gas_limit,
        calldata_hex=calldata_hex,
        value_wei=value_wei,
    )
    return res.to_dict()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True))
def sentinel_simulate_transaction(
    to_address: str,
    from_address: str = "0x0000000000000000000000000000000000000000",
    value_wei: int = 0,
    data: str = "0x",
    gas: int = 0,
    rpc_url: str = "",
    chain_id: int = 0,
) -> Dict[str, Any]:
    """Simulate transaction execution against an EVM JSON-RPC node without mutating state.

    Uses `eth_call` for success/revert and `eth_estimateGas` for gas usage. Select the
    network with `chain_id` (preferred) or a configured `rpc_url`; defaults to Arc Mainnet.
    `gas=0` lets the node choose the gas limit.
    """
    state = _get_state()
    target_rpc, resolved_chain = _resolve_rpc(state.settings, rpc_url, chain_id)
    sim = state.simulator(target_rpc).simulate_call(
        to=to_address,
        data=data,
        from_addr=from_address,
        value_wei=value_wei,
        gas=gas or None,
    )
    res = sim.to_dict()
    res["target_rpc"] = target_rpc
    res["chain_id"] = resolved_chain
    return res


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def sentinel_rpc_cache(
    action: Literal["get", "put", "stats"],
    key: str = "",
    value: str = "",
    ttl_seconds: float = -1.0,
) -> Dict[str, Any]:
    """Fixed-capacity C++ ring-buffer cache for RPC reads (FIFO eviction, 1024 slots).

    Actions:
    - 'get': Retrieve a cached payload by key (expired entries are misses).
    - 'put': Store a payload (key <= 127 bytes, value <= 511 bytes). `ttl_seconds` sets
      expiry; 0 = never, negative = server default (SENTINEL_CACHE_DEFAULT_TTL_SECONDS).
    - 'stats': Return capacity, count, and arena status.
    """
    state = _get_state()
    bridge = state.bridge
    if action == "get":
        val = bridge.cache_get(key)
        found = val is not None
        code = SentinelStatusCode.OK if found else SentinelStatusCode.ERR_CACHE_NOT_FOUND
        return {"action": "get", "key": key, "value": val or "", "status_code": int(code), "found": found}
    if action == "put":
        ttl = state.settings.cache_default_ttl_seconds if ttl_seconds < 0 else ttl_seconds
        code = bridge.cache_put_status(key, value, ttl_seconds=ttl)
        return {
            "action": "put",
            "key": key,
            "status_code": int(code),
            "status_name": code.name,
            "stored": code == SentinelStatusCode.OK,
            "ttl_seconds": ttl,
        }
    if action == "stats":
        stats = bridge.cache_stats()
        stats["action"] = "stats"
        return stats
    raise ValueError(f"Unknown cache action {action!r}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def sentinel_agent_guard(
    action: Literal["check", "authorize", "record", "status", "arc_status", "reset"],
    to_address: str = "",
    value_wei: int = 0,
    tx_hash: str = "",
) -> Dict[str, Any]:
    """Enforce session-wide financial spend limits, address filtering, and rate limits.

    Actions:
    - 'authorize': Atomically check a planned transaction AND reserve its value against
      the session budget. Use this before signing.
    - 'check': Dry-run the guard decision without reserving budget.
    - 'record': Record an executed transaction (increases cumulative spend only).
    - 'status' / 'arc_status': Query session spend, remaining budget, and rate tokens.
    - 'reset': Reset the session (disabled unless SENTINEL_ALLOW_AGENT_RESET=1).
    """
    state = _get_state()
    guard = state.guard
    if action == "check":
        return guard.check_transaction(target_address=to_address, value_wei=value_wei).to_dict()
    if action == "authorize":
        return guard.authorize(target_address=to_address, value_wei=value_wei, tx_ref=tx_hash).to_dict()
    if action == "record":
        guard.record_transaction(tx_hash=tx_hash, value_wei=value_wei)
        return {"status": "recorded", "tx_hash": tx_hash, "value_wei": value_wei}
    if action == "status":
        return guard.get_status()
    if action == "arc_status":
        status = guard.get_status()
        status["network"] = "Arc Mainnet"
        status["chain_id"] = ARC_CHAIN_ID
        status["gas_asset"] = ARC_GAS_TOKEN
        status["session_spend_usdc"] = base_units_to_usdc(status.get("session_spend_wei", 0))
        status["remaining_session_budget_usdc"] = base_units_to_usdc(status.get("remaining_session_budget_wei", 0))
        return status
    if action == "reset":
        if not state.settings.allow_agent_reset:
            logger.warning("guard.reset denied: agent-initiated reset is disabled")
            raise PermissionError(
                "Session reset is disabled for agents (operator can set SENTINEL_ALLOW_AGENT_RESET=1)"
            )
        guard.reset_session()
        return {"status": "reset"}
    raise ValueError(f"Unknown guard action {action!r}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
def sentinel_audit_invariants() -> Dict[str, Any]:
    """Execute static analysis verifying Power of 10 Safety Invariants on the C++ core.

    Audits maximum function lengths (<= 60 lines), assertion densities (>= 2 asserts/func),
    absence of dynamic heap allocation (malloc/new/free), recursion, and unbounded loops.
    """
    auditor = SafetyInvariantAuditor(find_csrc_dir())
    return auditor.audit().to_dict()


def main() -> None:
    """Run FastMCP server over stdio."""
    configure()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
