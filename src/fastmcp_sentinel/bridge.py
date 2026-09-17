import os
import time
import ctypes
from enum import IntEnum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class SentinelStatusCode(IntEnum):
    OK = 0
    ERR_NULL_PTR = -1
    ERR_CALLDATA_TOO_LARGE = -2
    ERR_VALUE_EXCEEDED = -3
    ERR_GAS_EXCEEDED = -4
    ERR_REENTRANCY_SIGNATURE = -5
    ERR_CACHE_FULL = -6
    ERR_CACHE_NOT_FOUND = -7
    ERR_BUFFER_TOO_SMALL = -8


class SentinelValidationResult(ctypes.Structure):
    _fields_ = [
        ("status_code", ctypes.c_int),
        ("selector", ctypes.c_uint32),
        ("gas_limit", ctypes.c_uint64),
        ("value_gwei", ctypes.c_uint64),
        ("reason", ctypes.c_char * 128),
    ]

    @property
    def reason_str(self) -> str:
        return self.reason.decode("utf-8", errors="replace").rstrip("\x00")

    @property
    def value_wei(self) -> int:
        return int(self.value_gwei) * 10**9


@dataclass
class ValidationSummary:
    is_valid: bool
    status_code: int
    status_name: str
    reason: str
    function_selector: str
    gas_limit: int
    value_wei: int
    latency_us: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status_code": self.status_code,
            "status_name": self.status_name,
            "reason": self.reason,
            "function_selector": self.function_selector,
            "gas_limit": self.gas_limit,
            "value_wei": self.value_wei,
            "latency_us": self.latency_us,
        }


class SentinelCacheEntry(ctypes.Structure):
    _fields_ = [
        ("key", ctypes.c_char * 128),
        ("value", ctypes.c_char * 512),
        ("timestamp_ns", ctypes.c_uint64),
        ("is_valid", ctypes.c_uint8),
    ]


class SentinelMemoryArena(ctypes.Structure):
    _fields_ = [
        ("entries", SentinelCacheEntry * 1024),
        ("count", ctypes.c_size_t),
        ("next_idx", ctypes.c_size_t),
        ("is_initialized", ctypes.c_uint8),
    ]


class SentinelBridge:
    def __init__(self, lib_path: Optional[str] = None):
        if lib_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            lib_path = os.path.join(base_dir, "csrc", "libsentinel_core.dylib")

        assert os.path.exists(lib_path), f"Native dynamic library missing at: {lib_path}"
        self._lib = ctypes.CDLL(lib_path)

        # Function signatures
        self._lib.sentinel_init_arena.argtypes = [ctypes.POINTER(SentinelMemoryArena)]
        self._lib.sentinel_init_arena.restype = ctypes.c_int

        self._lib.sentinel_reset_arena.argtypes = [ctypes.POINTER(SentinelMemoryArena)]
        self._lib.sentinel_reset_arena.restype = None

        self._lib.sentinel_validate_tx.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.POINTER(SentinelValidationResult),
        ]
        self._lib.sentinel_validate_tx.restype = ctypes.c_int

        self._lib.sentinel_cache_put.argtypes = [
            ctypes.POINTER(SentinelMemoryArena),
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint64,
        ]
        self._lib.sentinel_cache_put.restype = ctypes.c_int

        self._lib.sentinel_cache_get.argtypes = [
            ctypes.POINTER(SentinelMemoryArena),
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]
        self._lib.sentinel_cache_get.restype = ctypes.c_int

        self._arena = SentinelMemoryArena()
        rc = self._lib.sentinel_init_arena(ctypes.byref(self._arena))
        assert rc == 0, f"Failed to initialize SentinelMemoryArena: {rc}"
        self.is_initialized = True

    def close(self):
        if self.is_initialized:
            self._lib.sentinel_reset_arena(ctypes.byref(self._arena))
            self.is_initialized = False

    def __del__(self):
        self.close()

    def validate_tx(
        self,
        to_address: str,
        calldata: bytes,
        value_wei: int,
        gas_limit: int,
    ) -> SentinelValidationResult:
        assert self.is_initialized, "Bridge arena is not initialized"
        assert isinstance(to_address, str), "to_address must be a string"
        assert isinstance(calldata, (bytes, bytearray)), "calldata must be bytes"

        result = SentinelValidationResult()
        c_to = to_address.encode("utf-8")
        c_calldata = bytes(calldata)
        c_len = len(c_calldata)

        # Scale wei to Gwei (1 ETH = 10^9 Gwei) to prevent 64-bit integer overflow
        val_gwei = value_wei // 10**9 if value_wei >= 10**9 else (1 if value_wei > 0 else 0)

        self._lib.sentinel_validate_tx(
            c_to,
            c_calldata,
            ctypes.c_size_t(c_len),
            ctypes.c_uint64(val_gwei),
            ctypes.c_uint64(gas_limit),
            ctypes.byref(result),
        )
        return result

    def validate_transaction(
        self,
        to_address: str,
        value_eth: float = 0.0,
        gas_limit: int = 100000,
        calldata_hex: str = "0x",
    ) -> ValidationSummary:
        """High-level transaction validation with latency profiling."""
        t0 = time.perf_counter_ns()

        clean_hex = calldata_hex.strip()
        if clean_hex.startswith("0x") or clean_hex.startswith("0X"):
            clean_hex = clean_hex[2:]
        if len(clean_hex) % 2 != 0:
            clean_hex = "0" + clean_hex

        calldata_bytes = bytes.fromhex(clean_hex) if clean_hex else b""
        value_wei = int(value_eth * 10**18)

        raw_res = self.validate_tx(
            to_address=to_address,
            calldata=calldata_bytes,
            value_wei=value_wei,
            gas_limit=gas_limit,
        )
        t1 = time.perf_counter_ns()
        latency_us = round((t1 - t0) / 1000.0, 2)

        try:
            status_enum = SentinelStatusCode(raw_res.status_code)
            status_name = status_enum.name
        except ValueError:
            status_name = f"UNKNOWN({raw_res.status_code})"

        selector_str = f"0x{raw_res.selector:08x}" if raw_res.selector != 0 else "0x00000000"

        return ValidationSummary(
            is_valid=(raw_res.status_code == SentinelStatusCode.OK),
            status_code=raw_res.status_code,
            status_name=status_name,
            reason=raw_res.reason_str,
            function_selector=selector_str,
            gas_limit=raw_res.gas_limit,
            value_wei=value_wei,
            latency_us=latency_us,
        )

    def cache_put(self, key: str, value: str, timestamp_ns: Optional[int] = None) -> bool:
        assert self.is_initialized, "Bridge arena is not initialized"
        ts = timestamp_ns if timestamp_ns is not None else time.time_ns()
        rc = self._lib.sentinel_cache_put(
            ctypes.byref(self._arena),
            key.encode("utf-8"),
            value.encode("utf-8"),
            ctypes.c_uint64(ts),
        )
        return rc == 0

    def cache_get(self, key: str) -> Optional[str]:
        assert self.is_initialized, "Bridge arena is not initialized"
        buf = ctypes.create_string_buffer(512)
        rc = self._lib.sentinel_cache_get(
            ctypes.byref(self._arena),
            key.encode("utf-8"),
            buf,
            ctypes.c_size_t(512),
        )
        if rc == 0:
            return buf.value.decode("utf-8", errors="replace")
        return None

    def cache_stats(self) -> Dict[str, Any]:
        return {
            "capacity": 1024,
            "count": self._arena.count,
            "next_idx": self._arena.next_idx,
            "is_initialized": bool(self._arena.is_initialized),
        }


# Singleton accessor
_GLOBAL_BRIDGE: Optional[SentinelBridge] = None


def get_bridge() -> SentinelBridge:
    global _GLOBAL_BRIDGE
    if _GLOBAL_BRIDGE is None:
        _GLOBAL_BRIDGE = SentinelBridge()
    return _GLOBAL_BRIDGE
