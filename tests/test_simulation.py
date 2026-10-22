import pytest
import requests

from fastmcp_sentinel.simulation import RpcError, TransactionSimulator


def test_mock_simulation_success():
    sim = TransactionSimulator(rpc_url="mock://local")
    res = sim.simulate_call(
        to="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        data="0x70a082310000000000000000000000001234567890123456789012345678901234567890",  # balanceOf
        from_addr="0x0000000000000000000000000000000000000001",
    )
    assert res.success
    assert res.gas_used > 0
    assert res.revert_reason is None


def test_mock_simulation_revert_detected():
    sim = TransactionSimulator(rpc_url="mock://local")
    # Calldata intentionally flagged to mock a revert
    res = sim.simulate_call(
        to="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        data="0xa9059cbb_mock_revert_insufficient_allowance",
        from_addr="0x0000000000000000000000000000000000000001",
    )
    assert not res.success
    assert res.revert_reason is not None
    assert "reverted" in res.revert_reason.lower()


def test_revert_reason_decoder():
    sim = TransactionSimulator(rpc_url="mock://local")
    # ABI-encoded Error("Transfer failed")
    # selector: 0x08c379a0
    # offset: 32
    # length: 15
    # string: "Transfer failed"
    raw_revert = "0x08c379a00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000f5472616e73666572206661696c65640000000000000000000000000000000000"
    msg = sim.decode_revert_reason(raw_revert)
    assert msg == "Transfer failed"


# --- Live JSON-RPC path (network stubbed) ------------------------------------


TO = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"


def test_live_simulation_uses_estimate_gas_and_forwards_gas(fake_rpc):
    fake = fake_rpc({"eth_call": "0x01", "eth_estimateGas": "0xb411"})
    sim = TransactionSimulator(rpc_url="https://rpc.example")
    res = sim.simulate_call(to=TO, data="0x70a08231", value_wei=5, gas=60000)
    assert res.success and res.gas_used == 0xB411 and res.gas_estimated
    call_method, call_params = fake.calls[0]
    assert call_method == "eth_call"
    assert call_params[0]["gas"] == hex(60000)
    assert call_params[0]["value"] == "0x5"
    # gas cap is not forwarded to estimateGas (it would bound the estimate)
    assert "gas" not in fake.calls[1][1][0]


def test_live_simulation_estimate_failure_falls_back(fake_rpc):
    fake_rpc({"eth_call": "0x", "eth_estimateGas": RpcError("method not found")})
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate_call(to=TO, data="0x", gas=30000)
    assert res.success and res.gas_used == 30000 and not res.gas_estimated


REVERT_TRANSFER_FAILED = (
    "0x08c379a0"
    "0000000000000000000000000000000000000000000000000000000000000020"
    "000000000000000000000000000000000000000000000000000000000000000f"
    "5472616e73666572206661696c65640000000000000000000000000000000000"
)


@pytest.mark.parametrize(
    "err_data",
    [REVERT_TRANSFER_FAILED, {"data": REVERT_TRANSFER_FAILED}, {"originalError": {"data": REVERT_TRANSFER_FAILED}}],
)
def test_live_simulation_decodes_revert_from_any_error_shape(fake_rpc, err_data):
    fake_rpc({"eth_call": RpcError("execution reverted", err_data)})
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate_call(to=TO, data="0xa9059cbb")
    assert not res.success
    assert res.revert_reason == "Transfer failed"


def test_live_simulation_revert_without_data_uses_message(fake_rpc):
    fake_rpc({"eth_call": RpcError("execution reverted: Ownable: caller is not the owner")})
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate_call(to=TO, data="0x")
    assert res.revert_reason == "execution reverted: Ownable: caller is not the owner"


def test_live_simulation_network_error(fake_rpc):
    fake_rpc({"eth_call": requests.ConnectionError("boom")})
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate_call(to=TO, data="0x")
    assert not res.success and "Network RPC error" in res.revert_reason


def test_live_simulation_rejects_negative_value():
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate_call(to=TO, data="0x", value_wei=-1)
    assert not res.success and "value_wei" in res.revert_reason


@pytest.mark.parametrize(
    "data,expected",
    [
        ("0x4e487b71" + "0" * 62 + "11", "Arithmetic overflow/underflow"),
        ("0x4e487b71" + "0" * 62 + "51", "Call to uninitialized internal function"),
        ("0xfb8f41b2" + "0" * 64, "Execution reverted with custom error 0xfb8f41b2"),
        ("0x", "Execution reverted without reason"),
        (
            "0x08c379a0" + "0" * 62 + "20" + "0" * 62 + "ff" + "00" * 4,
            "Execution reverted with undecodable Error(string)",
        ),
    ],
)
def test_revert_decoder_variants(data, expected):
    assert TransactionSimulator(rpc_url="mock://x").decode_revert_reason(data) == expected
