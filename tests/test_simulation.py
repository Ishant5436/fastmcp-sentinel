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
