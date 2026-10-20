"""Arc Mainnet and FastMCP Sentinel Configuration.

Deterministic safety parameters and network endpoints for Arc Mainnet (Chain ID 5042)
with native USDC gas settlement and multi-chain fallback support.

USDC on Arc has two views of one balance:
- Native (msg.value, gas, eth_getBalance): 18 decimals, like ETH.
- ERC-20 interface at 0x3600...0000 (transfer/approve/balanceOf): 6 decimals.
Raw amounts differ by 10^12 between the two and must never be compared unconverted.
All spend accounting in this package uses native 18-decimal units.
"""

from __future__ import annotations

import os
from typing import Dict

# Arc Mainnet Network Parameters
ARC_CHAIN_ID: int = 5042
ARC_RPC_URL: str = os.environ.get("ARC_RPC_URL", "https://rpc.mainnet.arc.io")
ARC_EXPLORER_URL: str = "https://explorer.arc.io"
ARC_GAS_TOKEN: str = "USDC"
ARC_USDC_DECIMALS: int = 6  # ERC-20 interface decimals
ARC_NATIVE_DECIMALS: int = 18  # native balance / msg.value decimals
ARC_USDC_ERC20_ADDRESS: str = "0x3600000000000000000000000000000000000000"
ERC20_TO_NATIVE_SCALE: int = 10 ** (ARC_NATIVE_DECIMALS - ARC_USDC_DECIMALS)  # 10^12

# Arc Mainnet Session Financial Limits
ARC_MAX_SINGLE_TX_USDC: float = 10.0
ARC_MAX_SESSION_SPEND_USDC: float = 50.0
# ERC-20 base units (10^6), kept for callers that work with the ERC-20 interface
ARC_MAX_SINGLE_TX_BASE_UNITS: int = int(ARC_MAX_SINGLE_TX_USDC * (10**ARC_USDC_DECIMALS))
ARC_MAX_SESSION_SPEND_BASE_UNITS: int = int(ARC_MAX_SESSION_SPEND_USDC * (10**ARC_USDC_DECIMALS))
# Native units (10^18), used by the spend guard
ARC_MAX_SINGLE_TX_NATIVE: int = ARC_MAX_SINGLE_TX_BASE_UNITS * ERC20_TO_NATIVE_SCALE
ARC_MAX_SESSION_SPEND_NATIVE: int = ARC_MAX_SESSION_SPEND_BASE_UNITS * ERC20_TO_NATIVE_SCALE

# ERC-20 selectors that move or authorize movement of the caller's USDC
_SELECTOR_TRANSFER = "a9059cbb"  # transfer(address,uint256)
_SELECTOR_APPROVE = "095ea7b3"  # approve(address,uint256)
_SELECTOR_TRANSFER_FROM = "23b872dd"  # transferFrom(address,address,uint256)

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


def native_to_usdc(units: int) -> float:
    """Convert 18-decimal native USDC units (msg.value / wei-style) to human USDC."""
    assert units >= 0, "Native units cannot be negative"
    return float(units) / (10**ARC_NATIVE_DECIMALS)


def usdc_to_native(amount: float) -> int:
    """Convert human USDC amount to 18-decimal native units."""
    return usdc_to_base_units(amount) * ERC20_TO_NATIVE_SCALE


def usdc_exposure_native(to_address: str, value_wei: int, calldata_hex: str) -> int:
    """Total USDC a transaction can move, in native 18-decimal units.

    Counts the native value plus any ERC-20 transfer / approve / transferFrom amount when the
    call targets the Arc USDC interface. Approvals count in full because they authorize a
    spender to take that much. Malformed USDC calldata is treated as unbounded.
    """
    assert value_wei >= 0, "value_wei cannot be negative"
    exposure = value_wei
    if to_address.strip().lower() != ARC_USDC_ERC20_ADDRESS:
        return exposure

    data = calldata_hex.strip().lower()
    if data.startswith("0x"):
        data = data[2:]
    selector = data[:8]
    if selector in (_SELECTOR_TRANSFER, _SELECTOR_APPROVE):
        amount_hex = data[8 + 64 : 8 + 128]
    elif selector == _SELECTOR_TRANSFER_FROM:
        amount_hex = data[8 + 128 : 8 + 192]
    else:
        return exposure

    if len(amount_hex) != 64:
        return 2**256 - 1  # fail closed on truncated calldata
    try:
        amount = int(amount_hex, 16)
    except ValueError:
        return 2**256 - 1
    return exposure + amount * ERC20_TO_NATIVE_SCALE
