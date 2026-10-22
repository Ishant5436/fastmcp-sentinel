from __future__ import annotations

from collections.abc import Iterator

import pytest

from fastmcp_sentinel import server
from fastmcp_sentinel.config import SentinelSettings


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
