import time

import pytest
from fastmcp_sentinel.bridge import SentinelBridge, SentinelStatusCode

@pytest.fixture(scope="module")
def bridge():
    b = SentinelBridge()
    yield b
    b.close()

def test_bridge_initialization(bridge):
    assert bridge.is_initialized

def test_validate_valid_transaction(bridge):
    to_addr = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    calldata = bytes.fromhex("a9059cbb00000000000000000000000012345678901234567890123456789012345678900000000000000000000000000000000000000000000000000de0b6b3a7640000")
    val_wei = 10**18  # 1 ETH
    gas = 21000

    res = bridge.validate_tx(to_addr, calldata, val_wei, gas)
    assert res.status_code == SentinelStatusCode.OK
    assert hex(res.selector) == "0xa9059cbb"
    assert res.value_wei == val_wei
    assert res.gas_limit == gas
    assert "passed" in res.reason_str.lower()

def test_validate_value_ceiling_exceeded(bridge):
    to_addr = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    calldata = b""
    val_wei = 101 * 10**18  # 101 native units (> 100 unit ceiling)
    gas = 21000

    res = bridge.validate_tx(to_addr, calldata, val_wei, gas)
    assert res.status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED
    assert "100 native-unit" in res.reason_str.lower()

def test_validate_gas_ceiling_exceeded(bridge):
    to_addr = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    calldata = b""
    val_wei = 0
    gas = 20_000_000  # 20M gas (> 15M limit)

    res = bridge.validate_tx(to_addr, calldata, val_wei, gas)
    assert res.status_code == SentinelStatusCode.ERR_GAS_EXCEEDED
    assert "15m" in res.reason_str.lower()

def test_validate_calldata_too_large(bridge):
    to_addr = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    calldata = b"\x00" * 40000  # 40KB (> 32KB limit)
    val_wei = 0
    gas = 100000

    res = bridge.validate_tx(to_addr, calldata, val_wei, gas)
    assert res.status_code == SentinelStatusCode.ERR_CALLDATA_TOO_LARGE
    assert "32kb" in res.reason_str.lower()

def test_ring_cache_put_get(bridge):
    key = "eth_chainId:[]"
    val = '{"jsonrpc":"2.0","id":1,"result":"0xa4b1"}'  # Arbitrum One (42161)
    
    ok = bridge.cache_put(key, val)
    assert ok
    retrieved = bridge.cache_get(key)
    assert retrieved == val

def test_ring_cache_miss(bridge):
    retrieved = bridge.cache_get("non_existent_key")
    assert retrieved is None


def test_validate_value_just_above_ceiling_rejected(bridge):
    # 100 units + 1 wei must not round down under the ceiling
    res = bridge.validate_tx("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", b"", 100 * 10**18 + 1, 21000)
    assert res.status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED


def test_validate_value_does_not_wrap_uint64(bridge):
    # 2^64 gwei would wrap to 0 in c_uint64 without saturation
    res = bridge.validate_tx("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", b"", 2**64 * 10**9, 21000)
    assert res.status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED


def test_cache_put_overwrites_existing_key(bridge):
    bridge.cache_put("eth_blockNumber:[]", "0x100")
    bridge.cache_put("eth_blockNumber:[]", "0x200")
    assert bridge.cache_get("eth_blockNumber:[]") == "0x200"


def test_cache_overwrite_does_not_consume_slots(bridge):
    before = bridge.cache_stats()["count"]
    for i in range(5):
        bridge.cache_put("same-key", f"v{i}")
    assert bridge.cache_stats()["count"] <= before + 1


def test_cache_ttl_expiry(bridge):
    old_ts = time.time_ns() - 10 * 10**9  # written 10 seconds ago
    bridge.cache_put("ttl-key", "stale", timestamp_ns=old_ts)
    assert bridge.cache_get("ttl-key") == "stale"  # no expiry requested
    assert bridge.cache_get("ttl-key", max_age_ns=5 * 10**9) is None
    assert bridge.cache_get("ttl-key", max_age_ns=60 * 10**9) == "stale"


def test_cache_rejects_oversized_key(bridge):
    # Truncating long keys could alias two different requests to one entry
    long_a = "k" * 200 + "a"
    long_b = "k" * 200 + "b"
    assert bridge.cache_put(long_a, "A") is False
    assert bridge.cache_get(long_b) is None


def test_cache_ring_evicts_oldest():
    fresh = SentinelBridge()
    for i in range(1025):
        assert fresh.cache_put(f"key-{i}", str(i))
    assert fresh.cache_get("key-0") is None  # evicted by the 1025th write
    assert fresh.cache_get("key-1024") == "1024"
    assert fresh.cache_stats()["count"] == 1024
    fresh.close()
