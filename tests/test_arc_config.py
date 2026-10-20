import pytest
from fastmcp_sentinel.config import (
    ARC_CHAIN_ID,
    ARC_RPC_URL,
    ARC_GAS_TOKEN,
    ARC_USDC_DECIMALS,
    ARC_MAX_SINGLE_TX_BASE_UNITS,
    ARC_MAX_SESSION_SPEND_BASE_UNITS,
    ARC_MAX_SINGLE_TX_NATIVE,
    ARC_MAX_SESSION_SPEND_NATIVE,
    ARC_USDC_ERC20_ADDRESS,
    usdc_to_base_units,
    base_units_to_usdc,
    native_to_usdc,
    usdc_to_native,
    usdc_exposure_native,
)
from fastmcp_sentinel import simulation
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


def test_arc_simulation_default_rpc(monkeypatch):
    """Verify that sentinel_simulate_transaction defaults to Arc Mainnet when RPC is omitted."""
    called_urls = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"jsonrpc": "2.0", "id": 1, "result": "0x5208"}

    def fake_post(url, json, timeout):
        called_urls.append(url)
        return _Resp()

    # No real network access in unit tests
    monkeypatch.setattr(simulation.requests, "post", fake_post)
    res = sentinel_simulate_transaction(
        to_address="0x1111111111111111111111111111111111111111",
        data="0x",
    )
    assert res["chain_id"] == 5042
    assert res["target_rpc"] == ARC_RPC_URL
    assert called_urls and all(u == ARC_RPC_URL for u in called_urls)


def test_arc_agent_guard_status():
    """Verify sentinel_agent_guard reports Arc Mainnet metadata and USDC balances."""
    sentinel_agent_guard(action="reset")
    status = sentinel_agent_guard(action="arc_status")
    assert status["network"] == "Arc Mainnet"
    assert status["chain_id"] == 5042
    assert status["gas_asset"] == "USDC"
    assert "session_spend_usdc" in status
    assert "remaining_session_budget_usdc" in status
    assert status["max_single_tx_usdc"] == 10.0
    assert status["max_session_spend_usdc"] == 50.0


def test_arc_native_units_use_18_decimals():
    """Native USDC (msg.value) uses 18 decimals; the ERC-20 interface uses 6."""
    assert ARC_MAX_SINGLE_TX_NATIVE == 10 * 10**18
    assert ARC_MAX_SESSION_SPEND_NATIVE == 50 * 10**18
    assert native_to_usdc(10**18) == 1.0
    assert usdc_to_native(2.5) == 25 * 10**17


def test_arc_status_reports_real_usdc_amounts():
    """Spending 1 native USDC must show as 1 USDC, not 10^12 USDC."""
    sentinel_agent_guard(action="reset")
    sentinel_agent_guard(action="record", tx_hash="0x1", value_wei=10**18)
    status = sentinel_agent_guard(action="arc_status")
    assert status["session_spend_usdc"] == 1.0
    assert status["remaining_session_budget_usdc"] == 49.0
    sentinel_agent_guard(action="reset")


def test_guard_enforces_10_usdc_single_cap():
    sentinel_agent_guard(action="reset")
    to = "0x1111111111111111111111111111111111111111"
    assert sentinel_agent_guard(action="check", to_address=to, value_wei=10 * 10**18)["allowed"] is True
    assert sentinel_agent_guard(action="check", to_address=to, value_wei=10 * 10**18 + 1)["allowed"] is False


def _erc20_call(selector: str, *words: int) -> str:
    return "0x" + selector + "".join(f"{w:064x}" for w in words)


def test_usdc_erc20_transfer_counts_toward_spend():
    recipient = int("22" * 20, 16)
    data = _erc20_call("a9059cbb", recipient, 3 * 10**6)  # transfer 3 USDC (6 decimals)
    assert usdc_exposure_native(ARC_USDC_ERC20_ADDRESS, 0, data) == 3 * 10**18
    # Same calldata to a different contract is not USDC
    assert usdc_exposure_native("0x" + "11" * 20, 0, data) == 0


def test_usdc_erc20_approve_and_transfer_from_count():
    spender = int("33" * 20, 16)
    assert usdc_exposure_native(ARC_USDC_ERC20_ADDRESS, 0, _erc20_call("095ea7b3", spender, 5 * 10**6)) == 5 * 10**18
    data = _erc20_call("23b872dd", spender, spender, 7 * 10**6)
    assert usdc_exposure_native(ARC_USDC_ERC20_ADDRESS, 0, data) == 7 * 10**18


def test_usdc_truncated_calldata_fails_closed():
    assert usdc_exposure_native(ARC_USDC_ERC20_ADDRESS, 0, "0xa9059cbb1234") >= 2**255


def test_guard_blocks_large_usdc_erc20_transfer():
    sentinel_agent_guard(action="reset")
    data = _erc20_call("a9059cbb", int("22" * 20, 16), 25 * 10**6)  # 25 USDC > 10 USDC cap
    res = sentinel_agent_guard(action="check", to_address=ARC_USDC_ERC20_ADDRESS, calldata_hex=data)
    assert res["allowed"] is False
    assert res["status_name"] == "EXCEEDS_SINGLE_LIMIT"
