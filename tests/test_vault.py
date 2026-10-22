"""SentinelVault client: ABI encoding, artifact consistency, and live anvil integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import VAULT_ARTIFACT, abi_word
from fastmcp_sentinel import server
from fastmcp_sentinel.simulation import TransactionSimulator
from fastmcp_sentinel.vault import (
    PAYMENT_EVENT_TOPIC,
    SELECTORS,
    VAULT_ERRORS,
    VaultStatus,
    decode_check,
    decode_policy,
    decode_vault_error,
    encode_check,
    encode_memo,
    encode_pay,
    format_usdc,
    parse_usdc,
)

ROOT = Path(__file__).resolve().parent.parent

MERCHANT = "0x000000000000000000000000000000000000beef"


# --- pure encoding ------------------------------------------------------------


def test_encode_pay_layout():
    data = encode_pay(MERCHANT, 2_500_000, "inv-42")
    assert data.startswith("0x5e5571ac")
    body = data[10:]
    assert len(body) == 3 * 64
    assert body[:64] == MERCHANT[2:].rjust(64, "0")
    assert int(body[64:128], 16) == 2_500_000
    assert bytes.fromhex(body[128:]).rstrip(b"\0") == b"inv-42"


def test_encode_memo_hex_passthrough_and_limits():
    h = "0x" + "ab" * 32
    assert encode_memo(h) == "ab" * 32
    assert encode_memo("") == "0" * 64
    with pytest.raises(ValueError):
        encode_memo("x" * 33)


@pytest.mark.parametrize("bad", ["0x1234", "nothex", ""])
def test_encoders_reject_bad_addresses(bad):
    with pytest.raises(ValueError):
        encode_check(bad, 1)


@pytest.mark.parametrize(
    "text,units", [("1", 1_000_000), ("0.000001", 1), ("2.50", 2_500_000), (12.345678, 12_345_678)]
)
def test_parse_usdc_exact(text, units):
    assert parse_usdc(text) == units


@pytest.mark.parametrize("bad", ["0", "-1", "0.0000001", "nan", "inf", "abc"])
def test_parse_usdc_rejects(bad):
    with pytest.raises(ValueError):
        parse_usdc(bad)


def test_format_usdc():
    assert format_usdc(1_234_567) == "1.234567"


def test_decode_policy_and_check():
    words = [0xAA, 0xBB, 0x3600000000000000000000000000000000000000, 10, 50, 86400, 7, 3, 1, 0, 99]
    policy = decode_policy("0x" + "".join(format(w, "064x") for w in words))
    assert policy.owner.endswith("aa") and policy.token == "0x3600000000000000000000000000000000000000"
    assert policy.allowlist_enabled is True and policy.paused is False
    assert policy.to_dict()["remaining_in_period"] == 47
    status, remaining = decode_check("0x" + format(5, "064x") + format(12, "064x"))
    assert status == VaultStatus.EXCEEDS_PERIOD_LIMIT and remaining == 12
    with pytest.raises(ValueError):
        decode_policy("0x00")


def test_decode_vault_errors():
    assert decode_vault_error("0x0d9ab13f") == "NotAgent()"
    assert decode_vault_error("0x3fb1d2b1" + format(4, "064x")) == "PaymentRejected(EXCEEDS_SINGLE_LIMIT)"
    assert decode_vault_error("0xdeadbeef") is None
    sim = TransactionSimulator(rpc_url="mock://x")
    assert sim.decode_revert_reason("0x3fb1d2b1" + format(1, "064x")) == (
        "Execution reverted with PaymentRejected(PAUSED)"
    )


# --- consistency with the compiled contract -----------------------------------

needs_artifacts = pytest.mark.skipif(
    not VAULT_ARTIFACT.exists(), reason="contracts not built (run `forge build` in contracts/)"
)


def _keccak_hex(sig: str) -> str:
    keccak = pytest.importorskip("Crypto.Hash.keccak")
    return keccak.new(digest_bits=256, data=sig.encode()).hexdigest()


def _abi_sig(item: dict) -> str:
    def t(inp: dict) -> str:
        # enums surface as uint8 in the ABI; internalType keeps the Solidity name
        return inp["type"]

    return f"{item['name']}({','.join(t(i) for i in item['inputs'])})"


@needs_artifacts
def test_pinned_selectors_match_artifact():
    artifact = json.loads(VAULT_ARTIFACT.read_text())
    ids = artifact["methodIdentifiers"]
    for sig, selector in SELECTORS.items():
        if sig != "balanceOf(address)":
            assert ids[sig] == selector, sig


@needs_artifacts
def test_pinned_errors_and_event_match_artifact():
    abi = json.loads(VAULT_ARTIFACT.read_text())["abi"]
    errors = {_keccak_hex(_abi_sig(e))[:8]: _abi_sig(e) for e in abi if e["type"] == "error"}
    assert errors == VAULT_ERRORS
    payment = next(e for e in abi if e["type"] == "event" and e["name"] == "Payment")
    assert "0x" + _keccak_hex(_abi_sig(payment)) == PAYMENT_EVENT_TOPIC


@needs_artifacts
def test_status_enum_matches_contract():
    src = (ROOT / "contracts" / "src" / "SentinelVault.sol").read_text()
    block = src[src.index("enum Status {") : src.index("}", src.index("enum Status {"))]
    names = [line.strip().rstrip(",") for line in block.splitlines()[1:] if line.strip()]
    assert names == [s.name for s in VaultStatus]


# --- live integration against anvil -------------------------------------------


def _usdc_balance(anvil, token: str, who: str) -> int:
    return int(anvil.rpc("eth_call", [{"to": token, "data": "0x70a08231" + abi_word(who)}, "latest"]), 16)


def test_vault_tool_end_to_end(anvil, deployed):
    policy = server.sentinel_arc_vault(action="policy")
    assert policy["agent"].lower() == deployed["agent"].lower()
    assert policy["balance_usdc"] == "100.000000"
    assert policy["max_per_tx_usdc"] == "10.000000"

    check = server.sentinel_arc_vault(action="check", to_address=MERCHANT, amount_usdc="2.5")
    assert check["allowed"] is True and check["remaining_in_period_usdc"] == "50.000000"

    prepared = server.sentinel_arc_vault(
        action="prepare_payment", to_address=MERCHANT, amount_usdc="2.5", memo="invoice-7"
    )
    assert prepared["ready"] is True, prepared
    tx = prepared["unsigned_tx"]
    assert tx["chainId"] == 31337 and tx["to"].lower() == deployed["vault"].lower()

    # The agent wallet signs and broadcasts the prepared transaction (anvil unlocks its accounts).
    receipt = anvil.send(tx["from"], tx["data"], to=tx["to"])
    assert any(log["topics"][0] == PAYMENT_EVENT_TOPIC for log in receipt["logs"])
    assert _usdc_balance(anvil, deployed["token"], MERCHANT) == 2_500_000

    after = server.sentinel_arc_vault(action="policy")
    assert after["spent_in_period_usdc"] == "2.500000"


def test_vault_tool_reports_policy_rejections(anvil, deployed):
    over = server.sentinel_arc_vault(action="prepare_payment", to_address=MERCHANT, amount_usdc="10.000001")
    assert over["ready"] is False and over["vault_status"] == "EXCEEDS_SINGLE_LIMIT"

    pause = "0x" + deployed["abi"]["methodIdentifiers"]["pause()"]
    anvil.send(deployed["owner"], pause, to=deployed["vault"])
    paused = server.sentinel_arc_vault(action="check", to_address=MERCHANT, amount_usdc="1")
    assert paused["allowed"] is False and paused["vault_status"] == "PAUSED"


def test_vault_tool_requires_vault_address():
    with pytest.raises(ValueError, match="vault_address is required"):
        server.sentinel_arc_vault(action="policy")
