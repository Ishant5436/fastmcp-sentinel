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

        try:
            # 1. Simulate via eth_call
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_call",
                "params": [tx_obj, "latest"],
            }
            resp = requests.post(self.rpc_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            res_json = resp.json()

            if "error" in res_json:
                err_data = res_json["error"].get("data", "")
                reason = self.decode_revert_reason(str(err_data))
                return SimulationResult(
                    success=False,
                    gas_used=0,
                    return_data=str(err_data),
                    revert_reason=reason,
                    is_mock=False,
                )

            return_data = res_json.get("result", "0x")
            return SimulationResult(
                success=True,
                gas_used=45000,
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

    def simulate(
        self,
        to_address: str,
        from_address: str = "0x0000000000000000000000000000000000000000",
        value_wei: int = 0,
        data: str = "0x",
        gas: int = 21000,
        rpc_url: str = "",
    ) -> SimulationResult:
        """High-level dispatch supporting runtime RPC URL overrides."""
        target_sim = self
        if rpc_url and rpc_url != self.rpc_url:
            target_sim = TransactionSimulator(rpc_url=rpc_url, timeout=self.timeout)
        return target_sim.simulate_call(
            to=to_address,
            data=data,
            from_addr=from_address,
            value_wei=value_wei,
        )


# Canonical Alias
EvmSimulator = TransactionSimulator
