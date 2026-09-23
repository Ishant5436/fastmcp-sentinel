import pytest
from fastmcp_sentinel.config import (
    ARC_CHAIN_ID,
    ARC_RPC_URL,
    ARC_GAS_TOKEN,
    ARC_USDC_DECIMALS,
    ARC_MAX_SINGLE_TX_BASE_UNITS,
    ARC_MAX_SESSION_SPEND_BASE_UNITS,
    usdc_to_base_units,
    base_units_to_usdc,
)
from fastmcp_sentinel.server import sentinel_simulate_transaction, sentinel_agent_guard


def test_arc_network_constants():
    """Verify Arc Mainnet identity, gas token, and decimal invariants."""
    assert ARC_CHAIN_ID == 5042, "Arc Mainnet chain ID must be 5042"
    assert ARC_GAS_TOKEN == "USDC", "Arc Mainnet native gas token must be USDC"
    assert ARC_USDC_DECIMALS == 6, "USDC has 6 decimal places"
    assert ARC_MAX_SINGLE_TX_BASE_UNITS == 10_000_000, "10 USDC single cap is 10M base units"
    assert ARC_MAX_SESSION_SPEND_BASE_UNITS == 50_000_000, "50 USDC session cap is 50M base units"


def test_arc_usdc_conversions():
    """Verify lossless conversion between floating-point USDC and integer base units."""
    assert usdc_to_base_units(1.0) == 1_000_000
    assert usdc_to_base_units(0.5) == 500_000
    assert usdc_to_base_units(12.345678) == 12_345_678
    assert base_units_to_usdc(1_000_000) == 1.0
    assert base_units_to_usdc(500_000) == 0.5


def test_arc_simulation_default_rpc():
    """Verify that sentinel_simulate_transaction defaults to Arc Mainnet when RPC is omitted."""
    res = sentinel_simulate_transaction(
        to_address="0x1111111111111111111111111111111111111111",
        data="0x",
    )
    assert res["chain_id"] == 5042
    assert res["target_rpc"] == ARC_RPC_URL


def test_arc_agent_guard_status():
    """Verify sentinel_agent_guard reports Arc Mainnet metadata and USDC balances."""
    status = sentinel_agent_guard(action="arc_status")
    assert status["network"] == "Arc Mainnet"
    assert status["chain_id"] == 5042
    assert status["gas_asset"] == "USDC"
    assert "session_spend_usdc" in status
    assert "remaining_session_budget_usdc" in status
