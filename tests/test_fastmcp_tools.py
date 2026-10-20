import pytest
import asyncio
from fastmcp_sentinel.server import (
    mcp,
    sentinel_validate_calldata,
    sentinel_simulate_transaction,
    sentinel_rpc_cache,
    sentinel_agent_guard,
    sentinel_audit_invariants,
    sentinel_preflight,
)

@pytest.mark.anyio
async def test_tool_registration():
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "sentinel_validate_calldata",
        "sentinel_simulate_transaction",
        "sentinel_rpc_cache",
        "sentinel_agent_guard",
        "sentinel_audit_invariants",
        "sentinel_preflight",
    }
    assert expected.issubset(tool_names)

def test_tool_validate_calldata():
    # Valid transfer
    res = sentinel_validate_calldata(
        to_address="0x1111111111111111111111111111111111111111",
        value_native=1.5,
        gas_limit=100000,
        calldata_hex="0xa9059cbb00000000000000000000000022222222222222222222222222222222222222220000000000000000000000000000000000000000000000000000000000000001",
    )
    assert res["is_valid"] is True
    assert res["status_code"] == 0
    assert res["function_selector"] == "0xa9059cbb"
    assert res["latency_us"] >= 0

    # Value ceiling violation
    res_bad = sentinel_validate_calldata(
        to_address="0x1111111111111111111111111111111111111111",
        value_eth=150.0,
        gas_limit=100000,
        calldata_hex="0x",
    )
    assert res_bad["is_valid"] is False
    assert res_bad["status_code"] == -3
    assert "exceeds 100 native-unit ceiling" in res_bad["reason"]

def test_tool_simulate_transaction():
    # Mock successful call
    res = sentinel_simulate_transaction(
        to_address="0x1111111111111111111111111111111111111111",
        from_address="0x2222222222222222222222222222222222222222",
        value_wei=0,
        data="0x12345678",
        gas=50000,
        rpc_url="mock://success",
    )
    assert res["success"] is True
    assert res["gas_used"] == 21000

    # Mock revert call
    res_revert = sentinel_simulate_transaction(
        to_address="0x1111111111111111111111111111111111111111",
        rpc_url="mock://revert",
    )
    assert res_revert["success"] is False
    assert res_revert["revert_reason"] == "TransferFailed"

def test_tool_rpc_cache():
    # Put
    res_put = sentinel_rpc_cache(action="put", key="eth_chainId", value="0x1")
    assert res_put["status_code"] == 0

    # Get
    res_get = sentinel_rpc_cache(action="get", key="eth_chainId")
    assert res_get["status_code"] == 0
    assert res_get["value"] == "0x1"

    # Stats
    res_stats = sentinel_rpc_cache(action="stats")
    assert res_stats["capacity"] == 1024
    assert res_stats["count"] >= 1

def test_tool_agent_guard():
    # Status
    st = sentinel_agent_guard(action="status")
    assert "max_session_spend_wei" in st

    sentinel_agent_guard(action="reset")
    # Check valid
    chk = sentinel_agent_guard(action="check", to_address="0x1111111111111111111111111111111111111111", value_wei=10**17)
    assert chk["allowed"] is True

    # Record
    rec = sentinel_agent_guard(action="record", tx_hash="0xdeadbeef", value_wei=10**17)
    assert rec["status"] == "recorded"

    # Reset
    rst = sentinel_agent_guard(action="reset")
    assert rst["status"] == "reset"

def test_tool_audit_invariants():
    report = sentinel_audit_invariants()
    assert report["passed"] is True
    assert report["violations_count"] == 0
    assert report["functions_audited"] >= 6


def test_tool_validate_calldata_value_eth_alias():
    res = sentinel_validate_calldata(to_address="0x1111111111111111111111111111111111111111", value_eth=150.0)
    assert res["is_valid"] is False


def test_tool_rpc_cache_overwrite_and_ttl():
    sentinel_rpc_cache(action="put", key="eth_gasPrice", value="0x1")
    sentinel_rpc_cache(action="put", key="eth_gasPrice", value="0x2")
    assert sentinel_rpc_cache(action="get", key="eth_gasPrice")["value"] == "0x2"
    assert sentinel_rpc_cache(action="get", key="eth_gasPrice", max_age_seconds=60)["found"] is True


def test_tool_guard_rejects_negative_record():
    sentinel_agent_guard(action="reset")
    res = sentinel_agent_guard(action="record", tx_hash="0xbad", value_wei=-5 * 10**18)
    assert res["status"] == "rejected"
    assert sentinel_agent_guard(action="status")["session_spend_wei"] == 0


def test_tool_guard_reserve_confirm_release():
    sentinel_agent_guard(action="reset")
    recipient = "0x1111111111111111111111111111111111111111"
    res = sentinel_agent_guard(action="reserve", to_address=recipient, value_wei=4 * 10**18)
    assert res["allowed"] is True
    rid = res["reservation_id"]
    assert sentinel_agent_guard(action="status")["reserved_wei"] == 4 * 10**18

    assert sentinel_agent_guard(action="confirm", reservation_id=rid, tx_hash="0xabc")["status"] == "confirmed"
    st = sentinel_agent_guard(action="status")
    assert st["session_spend_wei"] == 4 * 10**18 and st["reserved_wei"] == 0
    # A reservation can only be finalized once
    assert sentinel_agent_guard(action="confirm", reservation_id=rid, tx_hash="0xabc")["status"] == "unknown_reservation"

    res2 = sentinel_agent_guard(action="reserve", to_address=recipient, value_wei=10**18)
    assert sentinel_agent_guard(action="release", reservation_id=res2["reservation_id"])["status"] == "released"
    assert sentinel_agent_guard(action="status")["reserved_wei"] == 0
    sentinel_agent_guard(action="reset")


def test_tool_preflight_success_reserves_spend():
    sentinel_agent_guard(action="reset")
    res = sentinel_preflight(
        to_address="0x1111111111111111111111111111111111111111",
        value_wei=2 * 10**18,
        rpc_url="mock://success",
    )
    assert res["approved"] is True
    assert res["reservation_id"]
    assert res["usdc_exposure"] == 2.0
    assert sentinel_agent_guard(action="status")["reserved_wei"] == 2 * 10**18
    sentinel_agent_guard(action="reset")


def test_tool_preflight_stops_at_simulation_without_reserving():
    sentinel_agent_guard(action="reset")
    res = sentinel_preflight(to_address="0x1111111111111111111111111111111111111111", rpc_url="mock://revert")
    assert res["approved"] is False
    assert res["failed_stage"] == "simulate"
    assert sentinel_agent_guard(action="status")["pending_reservations"] == 0


def test_tool_preflight_blocks_over_cap():
    sentinel_agent_guard(action="reset")
    res = sentinel_preflight(
        to_address="0x1111111111111111111111111111111111111111",
        value_wei=11 * 10**18,  # 11 USDC > 10 USDC single-tx cap
        rpc_url="mock://success",
    )
    assert res["approved"] is False
    assert res["failed_stage"] == "guard"
    sentinel_agent_guard(action="reset")
