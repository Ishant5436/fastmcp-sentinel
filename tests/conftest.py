from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests

from fastmcp_sentinel import server
from fastmcp_sentinel.config import SentinelSettings

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "contracts" / "out"
VAULT_ARTIFACT = OUT / "SentinelVault.sol" / "SentinelVault.json"
MOCK_ARTIFACT = OUT / "SentinelVault.t.sol" / "MockUSDC.json"


@pytest.fixture(autouse=True)
def secure_server() -> Iterator[SentinelSettings]:
    """Every test starts from a fresh server with production (fail-closed) defaults."""
    settings = server.configure(SentinelSettings())
    yield settings
    server.configure(SentinelSettings())


@pytest.fixture
def permissive_server() -> SentinelSettings:
    """Server configured the way an operator would for local development."""
    return server.configure(SentinelSettings(allow_mock_rpc=True, allow_agent_reset=True))


class FakeRpc:
    """Records JSON-RPC calls and replays canned responses keyed by method."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[tuple[str, list]] = []

    def __call__(self, method: str, params: list):
        self.calls.append((method, params))
        resp = self.responses[method]
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.fixture
def fake_rpc(monkeypatch):
    def install(responses: dict) -> FakeRpc:
        fake = FakeRpc(responses)
        monkeypatch.setattr("fastmcp_sentinel.simulation.TransactionSimulator._rpc", lambda self, m, p: fake(m, p))
        return fake

    return install


# --- local EVM (anvil) for contract integration tests ---------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Anvil:
    def __init__(self, url: str):
        self.url = url
        self.s = requests.Session()
        self.s.trust_env = False

    def rpc(self, method: str, params: list):
        body = self.s.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body["result"]

    def send(self, sender: str, data: str, to: str | None = None) -> dict:
        tx = {"from": sender, "data": data, "gas": hex(3_000_000)}
        if to:
            tx["to"] = to
        tx_hash = self.rpc("eth_sendTransaction", [tx])
        receipt = None
        for _ in range(100):
            receipt = self.rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                break
            time.sleep(0.05)
        assert receipt is not None and receipt["status"] == "0x1", receipt
        return receipt


@pytest.fixture(scope="session")
def anvil():
    binary = shutil.which("anvil")
    if binary is None or not MOCK_ARTIFACT.exists():
        pytest.skip("anvil and built contracts are required for the integration test")
    port = _free_port()
    proc = subprocess.Popen(
        [binary, "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    node = Anvil(f"http://127.0.0.1:{port}")
    try:
        for _ in range(100):
            try:
                node.rpc("eth_chainId", [])
                break
            except requests.ConnectionError:
                time.sleep(0.05)
        yield node
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def abi_word(v: int | str) -> str:
    if isinstance(v, str):
        return v[2:].lower().rjust(64, "0")
    return format(v, "064x")


@pytest.fixture
def deployed(anvil):
    owner, agent = anvil.rpc("eth_accounts", [])[:2]
    mock = json.loads(MOCK_ARTIFACT.read_text())
    vault_art = json.loads(VAULT_ARTIFACT.read_text())

    token = anvil.send(owner, mock["bytecode"]["object"])["contractAddress"]
    ctor = "".join(abi_word(x) for x in (token, owner, agent, 10_000_000, 50_000_000, 86_400))
    vault = anvil.send(owner, vault_art["bytecode"]["object"] + ctor)["contractAddress"]
    mint = "0x" + mock["methodIdentifiers"]["mint(address,uint256)"] + abi_word(vault) + abi_word(100_000_000)
    anvil.send(owner, mint, to=token)

    server.configure(SentinelSettings(rpc_endpoints={31337: anvil.url}, default_chain_id=31337, vault_address=vault))
    return {"owner": owner, "agent": agent, "token": token, "vault": vault, "abi": vault_art}
