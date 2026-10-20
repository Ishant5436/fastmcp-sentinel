import pytest
from fastmcp_sentinel.simulation import TransactionSimulator, SimulationResult

def test_mock_simulation_success():
    sim = TransactionSimulator(rpc_url="mock://local")
    res = sim.simulate_call(
        to="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        data="0x70a082310000000000000000000000001234567890123456789012345678901234567890", # balanceOf
        from_addr="0x0000000000000000000000000000000000000001"
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
        from_addr="0x0000000000000000000000000000000000000001"
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


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _fake_rpc(monkeypatch, responses):
    from fastmcp_sentinel import simulation

    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        return _FakeResp(responses[json["method"]])

    monkeypatch.setattr(simulation.requests, "post", fake_post)
    return calls


def test_live_simulation_uses_estimate_gas(monkeypatch):
    calls = _fake_rpc(monkeypatch, {
        "eth_call": {"jsonrpc": "2.0", "id": 1, "result": "0x01"},
        "eth_estimateGas": {"jsonrpc": "2.0", "id": 1, "result": hex(51234)},
    })
    sim = TransactionSimulator(rpc_url="https://rpc.example")
    res = sim.simulate(to_address="0x" + "11" * 20, data="0x12345678", gas=100000)
    assert res.success
    assert res.gas_used == 51234
    assert [c["method"] for c in calls] == ["eth_call", "eth_estimateGas"]
    assert calls[0]["params"][0]["gas"] == hex(100000)


def test_live_simulation_flags_out_of_gas(monkeypatch):
    _fake_rpc(monkeypatch, {
        "eth_call": {"jsonrpc": "2.0", "id": 1, "result": "0x"},
        "eth_estimateGas": {"jsonrpc": "2.0", "id": 1, "result": hex(90000)},
    })
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate(to_address="0x" + "11" * 20, gas=50000)
    assert not res.success
    assert "Out of gas" in res.revert_reason


def test_live_simulation_decodes_nested_revert_data(monkeypatch):
    revert = "0x08c379a00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000f5472616e73666572206661696c65640000000000000000000000000000000000"
    _fake_rpc(monkeypatch, {
        "eth_call": {"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted", "data": {"data": revert}}},
    })
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate(to_address="0x" + "11" * 20)
    assert not res.success
    assert res.revert_reason == "Transfer failed"


def test_live_simulation_falls_back_to_error_message(monkeypatch):
    _fake_rpc(monkeypatch, {
        "eth_call": {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "insufficient funds for gas * price + value"}},
    })
    res = TransactionSimulator(rpc_url="https://rpc.example").simulate(to_address="0x" + "11" * 20)
    assert not res.success
    assert "insufficient funds" in res.revert_reason
