import requests
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class SimulationResult:
    success: bool
    gas_used: int
    return_data: str
    revert_reason: Optional[str] = None
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "gas_used": self.gas_used,
            "return_data": self.return_data,
            "revert_reason": self.revert_reason,
            "is_mock": self.is_mock,
        }


class TransactionSimulator:
    def __init__(self, rpc_url: str = "https://arb1.arbitrum.io/rpc", timeout: float = 5.0):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.is_mock = rpc_url.startswith("mock://")

    def decode_revert_reason(self, revert_hex: str) -> str:
        if not revert_hex or not isinstance(revert_hex, str):
            return "Execution reverted without reason"

        hex_data = revert_hex.lower()
        if hex_data.startswith("0x"):
            hex_data = hex_data[2:]

        # Check for standard Error(string): 0x08c379a0
        if hex_data.startswith("08c379a0") and len(hex_data) >= 136:
            try:
                # Offset is at bytes 4..36 (chars 8..72), length at bytes 36..68 (chars 72..136)
                length = int(hex_data[72:136], 16)
                string_hex = hex_data[136 : 136 + length * 2]
                return bytes.fromhex(string_hex).decode("utf-8", errors="replace")
            except Exception:
                return "Execution reverted with undecodable Error(string)"

        # Check for Panic(uint256): 0x4e487b71
        if hex_data.startswith("4e487b71") and len(hex_data) >= 72:
            try:
                code = int(hex_data[8:72], 16)
                panic_codes = {
                    0x01: "Assert failed",
                    0x11: "Arithmetic overflow/underflow",
                    0x12: "Division by zero",
                    0x21: "Invalid enum value",
                    0x32: "Array out of bounds",
                }
                return panic_codes.get(code, f"Panic code: {hex(code)}")
            except Exception:
                return "Execution reverted with Panic(uint256)"

        return "Execution reverted"

    def simulate_call(
        self,
        to: str,
        data: str,
        from_addr: Optional[str] = None,
        value_wei: int = 0,
        gas: int = 0,
    ) -> SimulationResult:
        if self.is_mock:
            if "mock_revert" in data or "revert" in self.rpc_url:
                reason = "TransferFailed" if "revert" in self.rpc_url else "Execution reverted: simulated condition triggered"
                return SimulationResult(
                    success=False,
                    gas_used=0,
                    return_data="0x",
                    revert_reason=reason,
                    is_mock=True,
                )
            return SimulationResult(
                success=True,
                gas_used=21000,
                return_data="0x0000000000000000000000000000000000000000000000000000000000000001",
                revert_reason=None,
                is_mock=True,
            )

        # Live JSON-RPC execution
        tx_obj: Dict[str, Any] = {
            "to": to,
            "data": data,
            "value": hex(value_wei),
        }
        if from_addr:
            tx_obj["from"] = from_addr
        if gas > 0:
            tx_obj["gas"] = hex(gas)

        try:
            # 1. Simulate via eth_call against the latest state (read-only, no mutation)
            res_json = self._rpc("eth_call", [tx_obj, "latest"])
            if "error" in res_json:
                return self._revert_result(res_json["error"])
            return_data = res_json.get("result", "0x")

            # 2. Measure gas with eth_estimateGas instead of reporting a fixed number
            est_json = self._rpc("eth_estimateGas", [tx_obj])
            if "error" in est_json:
                return self._revert_result(est_json["error"])
            gas_used = int(est_json.get("result", "0x0"), 16)

            if gas > 0 and gas_used > gas:
                return SimulationResult(
                    success=False,
                    gas_used=gas_used,
                    return_data=return_data,
                    revert_reason=f"Out of gas: estimated {gas_used} exceeds gas limit {gas}",
                    is_mock=False,
                )
            return SimulationResult(
                success=True,
                gas_used=gas_used,
                return_data=return_data,
                revert_reason=None,
                is_mock=False,
            )
        except Exception as err:
            return SimulationResult(
                success=False,
                gas_used=0,
                return_data="0x",
                revert_reason=f"Network RPC error: {err}",
                is_mock=False,
            )

    def _rpc(self, method: str, params: list) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = requests.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _revert_result(self, error: Any) -> SimulationResult:
        """Build a failed result from a JSON-RPC error object.

        Nodes report revert data as `error.data` (hex string), nested as `error.data.data`,
        or only in `error.message`, depending on the client.
        """
        if not isinstance(error, dict):
            error = {"message": str(error)}
        err_data = error.get("data", "")
        if isinstance(err_data, dict):
            err_data = err_data.get("data", "")
        err_data = str(err_data or "")

        if err_data.startswith("0x") and len(err_data) > 2:
            reason = self.decode_revert_reason(err_data)
        else:
            reason = str(error.get("message") or "Execution reverted without reason")
        return SimulationResult(
            success=False,
            gas_used=0,
            return_data=err_data or "0x",
            revert_reason=reason,
            is_mock=False,
        )

    def simulate(
        self,
        to_address: str,
        from_address: str = "0x0000000000000000000000000000000000000000",
        value_wei: int = 0,
        data: str = "0x",
        gas: int = 0,
        rpc_url: str = "",
    ) -> SimulationResult:
        """High-level dispatch supporting runtime RPC URL overrides.

        `gas` is the caller's gas limit; 0 means no limit (the node estimates).
        """
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
