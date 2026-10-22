"""Zero-mutation EVM transaction simulation via JSON-RPC (``eth_call`` + ``eth_estimateGas``)."""

from __future__ import annotations

import itertools
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

ERROR_STRING_SELECTOR = "08c379a0"  # Error(string)
PANIC_SELECTOR = "4e487b71"  # Panic(uint256)

PANIC_CODES = {
    0x00: "Generic compiler panic",
    0x01: "Assert failed",
    0x11: "Arithmetic overflow/underflow",
    0x12: "Division by zero",
    0x21: "Invalid enum value",
    0x22: "Invalid storage byte array encoding",
    0x31: "pop() on empty array",
    0x32: "Array out of bounds",
    0x41: "Out of memory",
    0x51: "Call to uninitialized internal function",
}


@dataclass
class SimulationResult:
    success: bool
    gas_used: int
    return_data: str
    revert_reason: str | None = None
    is_mock: bool = False
    gas_estimated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "gas_used": self.gas_used,
            "gas_estimated": self.gas_estimated,
            "return_data": self.return_data,
            "revert_reason": self.revert_reason,
            "is_mock": self.is_mock,
        }


class RpcError(Exception):
    def __init__(self, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.data = data


def _extract_revert_data(data: Any) -> str:
    """Nodes disagree on where revert bytes live (``data``, ``data.data``, ``data.result``)."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for k in ("data", "result", "originalError"):
            v = data.get(k)
            found = _extract_revert_data(v)
            if found:
                return found
    return ""


class TransactionSimulator:
    _ids = itertools.count(1)

    def __init__(self, rpc_url: str = "https://arb1.arbitrum.io/rpc", timeout: float = 5.0):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.is_mock = rpc_url.startswith("mock://")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._session_lock = threading.Lock()

    def decode_revert_reason(self, revert_hex: str) -> str:
        if not revert_hex or not isinstance(revert_hex, str):
            return "Execution reverted without reason"

        hex_data = revert_hex.lower()
        if hex_data.startswith("0x"):
            hex_data = hex_data[2:]
        if not hex_data:
            return "Execution reverted without reason"

        # Standard Error(string): selector | offset | length | utf-8 bytes
        if hex_data.startswith(ERROR_STRING_SELECTOR) and len(hex_data) >= 136:
            try:
                offset = int(hex_data[8:72], 16)
                start = 8 + offset * 2
                length = int(hex_data[start : start + 64], 16)
                string_hex = hex_data[start + 64 : start + 64 + length * 2]
                if len(string_hex) != length * 2:
                    raise ValueError("truncated string")
                return bytes.fromhex(string_hex).decode("utf-8", errors="replace")
            except ValueError:
                return "Execution reverted with undecodable Error(string)"

        # Panic(uint256)
        if hex_data.startswith(PANIC_SELECTOR) and len(hex_data) >= 72:
            try:
                code = int(hex_data[8:72], 16)
            except ValueError:
                return "Execution reverted with Panic(uint256)"
            return PANIC_CODES.get(code, f"Panic code: {hex(code)}")

        # Custom Solidity error: surface the selector so callers can look it up.
        if len(hex_data) >= 8:
            return f"Execution reverted with custom error 0x{hex_data[:8]}"
        return "Execution reverted"

    def _rpc(self, method: str, params: list) -> Any:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        with self._session_lock:
            resp = self._session.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise RpcError(f"Malformed JSON-RPC response to {method}")
        if body.get("error"):
            err = body["error"]
            if isinstance(err, dict):
                raise RpcError(str(err.get("message", "JSON-RPC error")), err.get("data"))
            raise RpcError(str(err))
        return body.get("result")

    def _mock(self, data: str) -> SimulationResult:
        if "mock_revert" in data or "revert" in self.rpc_url:
            reason = (
                "TransferFailed" if "revert" in self.rpc_url else "Execution reverted: simulated condition triggered"
            )
            return SimulationResult(success=False, gas_used=0, return_data="0x", revert_reason=reason, is_mock=True)
        return SimulationResult(
            success=True,
            gas_used=21000,
            return_data="0x" + "0" * 63 + "1",
            revert_reason=None,
            is_mock=True,
        )

    def simulate_call(
        self,
        to: str,
        data: str,
        from_addr: str | None = None,
        value_wei: int = 0,
        gas: int | None = None,
    ) -> SimulationResult:
        if self.is_mock:
            return self._mock(data)

        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            return SimulationResult(False, 0, "0x", "Invalid value_wei: must be a non-negative integer")
        if gas is not None and (isinstance(gas, bool) or not isinstance(gas, int) or gas < 0):
            return SimulationResult(False, 0, "0x", "Invalid gas: must be a non-negative integer (0 = node default)")

        tx_obj: Dict[str, Any] = {"to": to, "data": data or "0x", "value": hex(value_wei)}
        if from_addr:
            tx_obj["from"] = from_addr
        if gas:
            tx_obj["gas"] = hex(gas)

        try:
            return_data = self._rpc("eth_call", [tx_obj, "latest"])
        except RpcError as err:
            raw = _extract_revert_data(err.data)
            reason = self.decode_revert_reason(raw) if raw else str(err)
            return SimulationResult(success=False, gas_used=0, return_data=raw or "0x", revert_reason=reason)
        except (requests.RequestException, ValueError) as err:
            logger.warning("simulation rpc failure url=%s err=%s", self.rpc_url, err)
            return SimulationResult(False, 0, "0x", f"Network RPC error: {err}")

        gas_used, estimated = self._estimate_gas(tx_obj, fallback=gas or 0)
        return SimulationResult(
            success=True,
            gas_used=gas_used,
            gas_estimated=estimated,
            return_data=return_data if isinstance(return_data, str) else "0x",
            revert_reason=None,
        )

    def _estimate_gas(self, tx_obj: Dict[str, Any], fallback: int) -> tuple[int, bool]:
        est_obj = {k: v for k, v in tx_obj.items() if k != "gas"}
        try:
            result = self._rpc("eth_estimateGas", [est_obj])
            return int(result, 16), True
        except (RpcError, requests.RequestException, ValueError, TypeError) as err:
            logger.info("eth_estimateGas unavailable url=%s err=%s", self.rpc_url, err)
            return fallback, False

    def simulate(
        self,
        to_address: str,
        from_address: str = "0x0000000000000000000000000000000000000000",
        value_wei: int = 0,
        data: str = "0x",
        gas: int = 0,
        rpc_url: str = "",
    ) -> SimulationResult:
        """High-level dispatch supporting runtime RPC URL overrides. ``gas=0`` lets the node choose."""
        target_sim = self
        if rpc_url and rpc_url != self.rpc_url:
            target_sim = TransactionSimulator(rpc_url=rpc_url, timeout=self.timeout)
        return target_sim.simulate_call(
            to=to_address,
            data=data,
            from_addr=from_address,
            value_wei=value_wei,
            gas=gas,
        )


# Canonical Alias
EvmSimulator = TransactionSimulator
