"""Arc Mainnet and FastMCP Sentinel Configuration.

Deterministic safety parameters and network endpoints for Arc Mainnet (Chain ID 5042)
with native USDC gas settlement and multi-chain fallback support.
"""

from __future__ import annotations

import os
from typing import Dict

# Arc Mainnet Network Parameters
ARC_CHAIN_ID: int = 5042
ARC_RPC_URL: str = os.environ.get("ARC_RPC_URL", "https://rpc.mainnet.arc.io")
ARC_EXPLORER_URL: str = "https://explorer.arc.io"
ARC_GAS_TOKEN: str = "USDC"
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
    return int(round(amount * (10**ARC_USDC_DECIMALS)))


def base_units_to_usdc(units: int) -> float:
    """Convert 6-decimal integer base units to human USDC float."""
    assert units >= 0, "Base units cannot be negative"
    return float(units) / (10**ARC_USDC_DECIMALS)
