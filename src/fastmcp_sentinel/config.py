"""Arc Mainnet and FastMCP Sentinel Configuration.

Deterministic safety parameters and network endpoints for Arc Mainnet (Chain ID 5042)
with native USDC gas settlement and multi-chain fallback support, plus the runtime
settings that control the server's security posture (all overridable by environment).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Mapping

# Arc Mainnet Network Parameters
ARC_CHAIN_ID: int = 5042
ARC_RPC_URL: str = os.environ.get("ARC_RPC_URL", "https://rpc.mainnet.arc.io")
ARC_EXPLORER_URL: str = "https://explorer.arc.io"
ARC_GAS_TOKEN: str = "USDC"  # noqa: S105 - asset symbol, not a secret
ARC_USDC_DECIMALS: int = 6

# Arc Mainnet Session Financial Limits (USDC native units: 10^6)
ARC_MAX_SINGLE_TX_USDC: float = 10.0
ARC_MAX_SESSION_SPEND_USDC: float = 50.0
ARC_MAX_SINGLE_TX_BASE_UNITS: int = int(ARC_MAX_SINGLE_TX_USDC * (10**ARC_USDC_DECIMALS))
ARC_MAX_SESSION_SPEND_BASE_UNITS: int = int(ARC_MAX_SESSION_SPEND_USDC * (10**ARC_USDC_DECIMALS))

# Multi-Chain RPC Directory
SUPPORTED_RPC_ENDPOINTS: Dict[int, str] = {
    5042: ARC_RPC_URL,
    1: os.environ.get("ETH_RPC_URL", "https://cloudflare-eth.com"),
    42161: os.environ.get("ARB_RPC_URL", "https://arb1.arbitrum.io/rpc"),
    8453: os.environ.get("BASE_RPC_URL", "https://mainnet.base.org"),
    10: os.environ.get("OP_RPC_URL", "https://mainnet.optimism.io"),
}


def usdc_to_base_units(amount: float) -> int:
    """Convert human USDC amount to 6-decimal integer base units."""
    assert amount >= 0.0, "USDC amount cannot be negative"
    assert amount < 1_000_000_000.0, "USDC amount exceeds safety threshold"
    return round(amount * (10**ARC_USDC_DECIMALS))


def base_units_to_usdc(units: int) -> float:
    """Convert 6-decimal integer base units to human USDC float."""
    assert units >= 0, "Base units cannot be negative"
    return float(units) / (10**ARC_USDC_DECIMALS)


class ConfigError(ValueError):
    """Raised when an environment variable holds an invalid value."""


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean (got {raw!r})")


def _env_int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = int(raw.strip(), 0)
    except ValueError as err:
        raise ConfigError(f"{name} must be an integer (got {raw!r})") from err
    if val < minimum:
        raise ConfigError(f"{name} must be >= {minimum} (got {val})")
    return val


def _env_float(env: Mapping[str, str], name: str, default: float, minimum: float = 0.0) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = float(raw.strip())
    except ValueError as err:
        raise ConfigError(f"{name} must be a number (got {raw!r})") from err
    if not val >= minimum:  # also rejects NaN
        raise ConfigError(f"{name} must be >= {minimum} (got {raw!r})")
    return val


def _env_addresses(env: Mapping[str, str], name: str) -> FrozenSet[str]:
    raw = env.get(name, "")
    return frozenset(a.strip().lower() for a in raw.split(",") if a.strip())


@dataclass(frozen=True)
class SentinelSettings:
    """Runtime security posture of the Sentinel server.

    Defaults are fail-closed: an agent cannot reset its own budget, point the
    simulator at arbitrary URLs, or use the mock simulator unless the operator
    explicitly opts in via environment variables.
    """

    max_single_tx_wei: int = 10**18
    max_session_spend_wei: int = 5 * 10**18
    rate_limit_per_minute: int = 60
    burst_limit: int = 10
    blocked_addresses: FrozenSet[str] = field(default_factory=frozenset)
    allowed_addresses: FrozenSet[str] = field(default_factory=frozenset)
    allow_agent_reset: bool = False
    allow_custom_rpc: bool = False
    allow_mock_rpc: bool = False
    rpc_timeout_seconds: float = 5.0
    cache_default_ttl_seconds: float = 0.0
    default_rpc_url: str = ARC_RPC_URL
    rpc_endpoints: Mapping[int, str] = field(default_factory=lambda: dict(SUPPORTED_RPC_ENDPOINTS))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SentinelSettings:
        e = os.environ if env is None else env
        return cls(
            max_single_tx_wei=_env_int(e, "SENTINEL_MAX_SINGLE_TX_WEI", cls.max_single_tx_wei),
            max_session_spend_wei=_env_int(e, "SENTINEL_MAX_SESSION_SPEND_WEI", cls.max_session_spend_wei),
            rate_limit_per_minute=_env_int(e, "SENTINEL_RATE_LIMIT_PER_MINUTE", cls.rate_limit_per_minute, 1),
            burst_limit=_env_int(e, "SENTINEL_BURST_LIMIT", cls.burst_limit, 1),
            blocked_addresses=_env_addresses(e, "SENTINEL_BLOCKED_ADDRESSES"),
            allowed_addresses=_env_addresses(e, "SENTINEL_ALLOWED_ADDRESSES"),
            allow_agent_reset=_env_bool(e, "SENTINEL_ALLOW_AGENT_RESET", False),
            allow_custom_rpc=_env_bool(e, "SENTINEL_ALLOW_CUSTOM_RPC", False),
            allow_mock_rpc=_env_bool(e, "SENTINEL_ALLOW_MOCK_RPC", False),
            rpc_timeout_seconds=_env_float(e, "SENTINEL_RPC_TIMEOUT_SECONDS", cls.rpc_timeout_seconds, 0.1),
            cache_default_ttl_seconds=_env_float(e, "SENTINEL_CACHE_DEFAULT_TTL_SECONDS", 0.0),
            default_rpc_url=e.get("ARC_RPC_URL", ARC_RPC_URL),
        )
