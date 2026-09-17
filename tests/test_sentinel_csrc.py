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
    val_wei = 101 * 10**18  # 101 ETH (> 100 ETH limit)
    gas = 21000

    res = bridge.validate_tx(to_addr, calldata, val_wei, gas)
    assert res.status_code == SentinelStatusCode.ERR_VALUE_EXCEEDED
    assert "100 eth" in res.reason_str.lower()

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

def test_lru_cache_put_get(bridge):
    key = "eth_chainId:[]"
    val = '{"jsonrpc":"2.0","id":1,"result":"0xa4b1"}'  # Arbitrum One (42161)
    
    ok = bridge.cache_put(key, val)
    assert ok
    retrieved = bridge.cache_get(key)
    assert retrieved == val

def test_lru_cache_miss(bridge):
    retrieved = bridge.cache_get("non_existent_key")
    assert retrieved is None
