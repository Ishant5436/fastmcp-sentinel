"""Regression tests for safety bypasses fixed in the hardening pass."""

from __future__ import annotations

import threading
import time

import pytest

from fastmcp_sentinel import server
from fastmcp_sentinel.bridge import UINT64_MAX, SentinelBridge, SentinelStatusCode
from fastmcp_sentinel.config import ConfigError, SentinelSettings
from fastmcp_sentinel.guard import GuardConfig, GuardStatusCode, StatefulAgentGuard

ADDR = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
OTHER = "0x1111111111111111111111111111111111111111"


@pytest.fixture(scope="module")
def bridge():
    b = SentinelBridge()
    yield b
    b.close()


# --- C++ validation gate -----------------------------------------------------


@pytest.mark.parametrize(
    "value_wei",
    [
        2**64 * 10**9 + 10**9,  # would wrap modulo 2**64 to 1 gwei
        UINT64_MAX * 10**9 + 1,
        10**40,
    ],
)
def test_huge_value_cannot_wrap_past_ceiling(bridge, value_wei):
    res = bridge.validate_tx(ADDR, b"", value_wei, 21000)
    assert res.status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED


def test_fractional_gwei_rounds_up_at_ceiling(bridge):
    ceiling_wei = 100 * 10**18
    assert bridge.validate_tx(ADDR, b"", ceiling_wei, 21000).status_code == SentinelStatusCode.OK
    assert bridge.validate_tx(ADDR, b"", ceiling_wei + 1, 21000).status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED


def test_huge_gas_cannot_wrap_past_ceiling(bridge):
    res = bridge.validate_tx(ADDR, b"", 0, 2**64 + 100)
    assert res.status_code == SentinelStatusCode.ERR_GAS_EXCEEDED


@pytest.mark.parametrize("value_wei,gas", [(-1, 21000), (0, -1)])
def test_negative_inputs_rejected_by_low_level_api(bridge, value_wei, gas):
    with pytest.raises(ValueError):
        bridge.validate_tx(ADDR, b"", value_wei, gas)


@pytest.mark.parametrize("addr", ["", "0x1234", "not-an-address", "0x" + "zz" * 20, ADDR + "00", ADDR[2:] + "00"])
def test_invalid_target_address_rejected(addr):
    res = server.sentinel_validate_calldata(to_address=addr)
    assert res["is_valid"] is False
    assert res["status_name"] == "ERR_INVALID_ADDRESS"


@pytest.mark.parametrize("data", ["0x12", "0x123456", "0xzz", "0x123"])
def test_malformed_calldata_rejected(data):
    res = server.sentinel_validate_calldata(to_address=ADDR, calldata_hex=data)
    assert res["is_valid"] is False
    assert res["status_name"] == "ERR_MALFORMED_CALLDATA"


@pytest.mark.parametrize("value_eth", [float("nan"), float("inf"), -1.0])
def test_non_finite_or_negative_eth_rejected(value_eth):
    res = server.sentinel_validate_calldata(to_address=ADDR, value_eth=value_eth)
    assert res["is_valid"] is False
    assert res["status_name"] == "ERR_INVALID_ARGUMENT"


def test_value_eth_converted_exactly():
    # 0.1 * 10**18 in binary floating point is 100000000000000005551; Decimal keeps it exact.
    res = server.sentinel_validate_calldata(to_address=ADDR, value_eth=0.1)
    assert res["value_wei"] == 10**17


def test_value_wei_takes_precedence():
    res = server.sentinel_validate_calldata(to_address=ADDR, value_eth=0.0, value_wei=101 * 10**18)
    assert res["status_name"] == "ERR_VALUE_EXCEEDED"


# --- Native cache ------------------------------------------------------------


def test_cache_overwrite_returns_latest(bridge):
    assert bridge.cache_put("dup", "old")
    assert bridge.cache_put("dup", "new")
    assert bridge.cache_get("dup") == "new"


def test_cache_rejects_instead_of_truncating(bridge):
    assert bridge.cache_put_status("big", "x" * 512) == SentinelStatusCode.ERR_BUFFER_TOO_SMALL
    assert bridge.cache_put_status("k" * 128, "v") == SentinelStatusCode.ERR_BUFFER_TOO_SMALL
    assert bridge.cache_put_status("", "v") == SentinelStatusCode.ERR_INVALID_ARGUMENT
    assert bridge.cache_get("big") is None
    assert bridge.cache_put("max", "x" * 511)
    assert bridge.cache_get("max") == "x" * 511


def test_cache_ttl_expires(bridge):
    assert bridge.cache_put("short", "v", ttl_seconds=0.05)
    assert bridge.cache_get("short") == "v"
    time.sleep(0.08)
    assert bridge.cache_get("short") is None


def test_cache_is_thread_safe(bridge):
    errors: list[str] = []

    def worker(n: int) -> None:
        for i in range(300):
            key = f"t{n}-{i % 20}"
            if not bridge.cache_put(key, str(i)):
                errors.append(f"put failed {key}")
            got = bridge.cache_get(key)
            if got is not None and not got.isdigit():
                errors.append(f"corrupt {key}={got!r}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_bridge_rejects_wrong_library(tmp_path):
    bogus = tmp_path / "libbogus.so"
    bogus.write_bytes(b"not a shared object")
    with pytest.raises(RuntimeError):
        SentinelBridge(lib_path=bogus)


# --- Agent guard -------------------------------------------------------------


def test_negative_record_cannot_inflate_budget():
    with pytest.raises(ValueError):
        server.sentinel_agent_guard(action="record", value_wei=-(10**20))
    assert server.sentinel_agent_guard(action="status")["remaining_session_budget_wei"] == 5 * 10**18


def test_negative_check_rejected():
    res = server.sentinel_agent_guard(action="check", to_address=OTHER, value_wei=-1)
    assert res["allowed"] is False
    assert res["status_name"] == "INVALID_VALUE"


def test_agent_cannot_reset_budget_by_default():
    server.sentinel_agent_guard(action="authorize", to_address=OTHER, value_wei=10**18)
    with pytest.raises(PermissionError):
        server.sentinel_agent_guard(action="reset")
    assert server.sentinel_agent_guard(action="status")["session_spend_wei"] == 10**18


def test_reset_allowed_when_operator_opts_in(permissive_server):
    server.sentinel_agent_guard(action="authorize", to_address=OTHER, value_wei=10**18)
    assert server.sentinel_agent_guard(action="reset") == {"status": "reset"}
    assert server.sentinel_agent_guard(action="status")["session_spend_wei"] == 0


def test_authorize_reserves_budget_atomically():
    guard = StatefulAgentGuard(GuardConfig(max_single_tx_wei=10, max_session_spend_wei=100, burst_limit=1000))
    allowed = []

    def worker() -> None:
        for _ in range(50):
            if guard.authorize(OTHER, 1).allowed:
                allowed.append(1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 100
    assert guard.get_status()["session_spend_wei"] == 100


def test_guard_rejects_invalid_address():
    guard = StatefulAgentGuard()
    res = guard.check_transaction("0xnothex", 0)
    assert res.status_code == GuardStatusCode.INVALID_ADDRESS


def test_guard_address_lists_are_case_insensitive():
    blocked = "0xABCDEF0000000000000000000000000000000001"
    guard = StatefulAgentGuard(GuardConfig(blacklist={blocked}))
    assert guard.check_transaction(blocked.lower(), 0).status_code == GuardStatusCode.BLACKLISTED_RECIPIENT


# --- Simulation egress policy ------------------------------------------------


def test_mock_rpc_disabled_by_default():
    with pytest.raises(ValueError, match="Mock simulation is disabled"):
        server.sentinel_simulate_transaction(to_address=ADDR, rpc_url="mock://anything")


@pytest.mark.parametrize(
    "url", ["http://169.254.169.254/latest/meta-data", "http://localhost:8545", "file:///etc/passwd"]
)
def test_arbitrary_rpc_urls_blocked_by_default(url):
    with pytest.raises(ValueError, match="not a configured endpoint"):
        server.sentinel_simulate_transaction(to_address=ADDR, rpc_url=url)


def test_custom_rpc_requires_http_scheme():
    server.configure(SentinelSettings(allow_custom_rpc=True))
    with pytest.raises(ValueError, match="http or https"):
        server.sentinel_simulate_transaction(to_address=ADDR, rpc_url="file:///etc/passwd")


def test_chain_id_selects_configured_endpoint(fake_rpc):
    fake_rpc({"eth_call": "0x", "eth_estimateGas": "0x5208"})
    res = server.sentinel_simulate_transaction(to_address=ADDR, chain_id=42161)
    assert res["chain_id"] == 42161
    assert res["target_rpc"] == server._get_state().settings.rpc_endpoints[42161]
    with pytest.raises(ValueError, match="Unsupported chain_id"):
        server.sentinel_simulate_transaction(to_address=ADDR, chain_id=999999)


# --- Settings ----------------------------------------------------------------


def test_settings_from_env():
    s = SentinelSettings.from_env(
        {
            "SENTINEL_MAX_SINGLE_TX_WEI": "0x10",
            "SENTINEL_ALLOW_AGENT_RESET": "true",
            "SENTINEL_BLOCKED_ADDRESSES": f" {ADDR.upper()} , ",
        }
    )
    assert s.max_single_tx_wei == 16
    assert s.allow_agent_reset is True
    assert s.allow_mock_rpc is False
    assert s.blocked_addresses == frozenset({ADDR})


@pytest.mark.parametrize(
    "env",
    [
        {"SENTINEL_ALLOW_AGENT_RESET": "maybe"},
        {"SENTINEL_MAX_SESSION_SPEND_WEI": "-1"},
        {"SENTINEL_BURST_LIMIT": "0"},
        {"SENTINEL_RPC_TIMEOUT_SECONDS": "nan"},
    ],
)
def test_settings_reject_invalid_env(env):
    with pytest.raises(ConfigError):
        SentinelSettings.from_env(env)
