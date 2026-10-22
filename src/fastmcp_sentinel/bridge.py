"""ctypes bridge to the C++ invariant core (``csrc/sentinel_core.cpp``)."""

from __future__ import annotations

import ctypes
import math
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict

from fastmcp_sentinel.paths import find_library

# Must match SENTINEL_ABI_VERSION in csrc/sentinel_core.hpp.
EXPECTED_ABI_VERSION = 2
CACHE_CAPACITY = 1024
MAX_KEY_LEN = 128
MAX_VAL_LEN = 512
UINT64_MAX = 2**64 - 1
WEI_PER_GWEI = 10**9
WEI_PER_ETH = 10**18


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
    ERR_INVALID_ADDRESS = -9
    ERR_MALFORMED_CALLDATA = -10
    ERR_INVALID_ARGUMENT = -11
    ERR_NOT_INITIALIZED = -12


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
        return bytes(self.reason).decode("utf-8", errors="replace").rstrip("\x00")

    @property
    def value_wei(self) -> int:
        return int(self.value_gwei) * WEI_PER_GWEI


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
        ("key", ctypes.c_char * MAX_KEY_LEN),
        ("value", ctypes.c_char * MAX_VAL_LEN),
        ("expires_at_ns", ctypes.c_uint64),
        ("is_valid", ctypes.c_uint8),
    ]


class SentinelMemoryArena(ctypes.Structure):
    _fields_ = [
        ("entries", SentinelCacheEntry * CACHE_CAPACITY),
        ("count", ctypes.c_size_t),
        ("next_idx", ctypes.c_size_t),
        ("is_initialized", ctypes.c_uint8),
    ]


class NativeLibraryError(RuntimeError):
    """The native library is missing or incompatible with this bridge."""


def _status_name(code: int) -> str:
    try:
        return SentinelStatusCode(code).name
    except ValueError:
        return f"UNKNOWN({code})"


def _eth_to_wei(value_eth: float | int | str) -> int:
    """Exact ETH -> wei conversion (no binary floating point rounding)."""
    if isinstance(value_eth, float) and not math.isfinite(value_eth):
        raise ValueError("value_eth must be finite")
    try:
        dec = Decimal(str(value_eth))
    except InvalidOperation as err:
        raise ValueError(f"value_eth is not a number: {value_eth!r}") from err
    wei = dec * WEI_PER_ETH
    if wei != wei.to_integral_value():
        raise ValueError("value_eth has more than 18 decimal places")
    return int(wei)


def _parse_calldata(calldata_hex: str) -> bytes:
    clean = calldata_hex.strip()
    if clean[:2] in ("0x", "0X"):
        clean = clean[2:]
    if len(clean) % 2 != 0:
        raise ValueError("calldata hex has an odd number of digits")
    return bytes.fromhex(clean)


class SentinelBridge:
    """Owns one native memory arena. Cache operations are serialized by a lock
    because ctypes releases the GIL while native code runs."""

    def __init__(self, lib_path: str | Path | None = None):
        path = Path(lib_path) if lib_path is not None else find_library()
        if not path.is_file():
            raise NativeLibraryError(f"Native dynamic library missing at: {path}")
        try:
            self._lib = ctypes.CDLL(str(path))
        except OSError as err:
            raise NativeLibraryError(f"Failed to load native library {path}: {err}") from err
        self.lib_path = path
        self._lock = threading.Lock()
        self.is_initialized = False
        self._bind_symbols()
        self._check_abi()

        self._arena = SentinelMemoryArena()
        rc = self._lib.sentinel_init_arena(ctypes.byref(self._arena))
        if rc != SentinelStatusCode.OK:
            raise NativeLibraryError(f"Failed to initialize SentinelMemoryArena: {_status_name(rc)}")
        self.is_initialized = True

    def _bind_symbols(self) -> None:
        lib = self._lib
        try:
            lib.sentinel_abi_version.argtypes = []
            lib.sentinel_abi_version.restype = ctypes.c_uint32
        except AttributeError as err:
            raise NativeLibraryError(f"{self.lib_path} predates ABI versioning; rebuild it (`make csrc`)") from err
        lib.sentinel_arena_size.argtypes = []
        lib.sentinel_arena_size.restype = ctypes.c_size_t
        lib.sentinel_cache_capacity.argtypes = []
        lib.sentinel_cache_capacity.restype = ctypes.c_size_t

        lib.sentinel_init_arena.argtypes = [ctypes.POINTER(SentinelMemoryArena)]
        lib.sentinel_init_arena.restype = ctypes.c_int
        lib.sentinel_reset_arena.argtypes = [ctypes.POINTER(SentinelMemoryArena)]
        lib.sentinel_reset_arena.restype = None

        lib.sentinel_validate_tx.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.POINTER(SentinelValidationResult),
        ]
        lib.sentinel_validate_tx.restype = ctypes.c_int

        lib.sentinel_cache_put.argtypes = [
            ctypes.POINTER(SentinelMemoryArena),
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint64,
        ]
        lib.sentinel_cache_put.restype = ctypes.c_int

        lib.sentinel_cache_get.argtypes = [
            ctypes.POINTER(SentinelMemoryArena),
            ctypes.c_char_p,
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]
        lib.sentinel_cache_get.restype = ctypes.c_int

    def _check_abi(self) -> None:
        version = self._lib.sentinel_abi_version()
        if version != EXPECTED_ABI_VERSION:
            raise NativeLibraryError(
                f"ABI mismatch: library {self.lib_path} is v{version}, bridge expects v{EXPECTED_ABI_VERSION}"
            )
        native_size = self._lib.sentinel_arena_size()
        if native_size != ctypes.sizeof(SentinelMemoryArena):
            raise NativeLibraryError(
                f"Struct layout mismatch: native arena is {native_size} bytes, "
                f"ctypes arena is {ctypes.sizeof(SentinelMemoryArena)} bytes"
            )
        if self._lib.sentinel_cache_capacity() != CACHE_CAPACITY:
            raise NativeLibraryError("Cache capacity mismatch between native library and bridge")

    def close(self) -> None:
        if getattr(self, "is_initialized", False):
            with self._lock:
                self._lib.sentinel_reset_arena(ctypes.byref(self._arena))
                self.is_initialized = False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: S110  # pragma: no cover - interpreter shutdown
            pass

    def validate_tx(
        self,
        to_address: str,
        calldata: bytes,
        value_wei: int,
        gas_limit: int,
    ) -> SentinelValidationResult:
        """Low-level validation. Raises ``ValueError`` for negative/non-integer inputs."""
        if not isinstance(to_address, str):
            raise TypeError("to_address must be a string")
        if not isinstance(calldata, (bytes, bytearray)):
            raise TypeError("calldata must be bytes")
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            raise ValueError("value_wei must be a non-negative integer")
        if isinstance(gas_limit, bool) or not isinstance(gas_limit, int) or gas_limit < 0:
            raise ValueError("gas_limit must be a non-negative integer")

        # Round partial gwei UP and saturate at UINT64_MAX so that neither
        # truncation nor ctypes' silent modulo-2**64 wrapping can turn an
        # oversized value into an acceptable one.
        value_gwei = min(-(-value_wei // WEI_PER_GWEI), UINT64_MAX)
        gas = min(gas_limit, UINT64_MAX)

        result = SentinelValidationResult()
        c_calldata = bytes(calldata)
        self._lib.sentinel_validate_tx(
            to_address.encode("utf-8"),
            c_calldata,
            ctypes.c_size_t(len(c_calldata)),
            ctypes.c_uint64(value_gwei),
            ctypes.c_uint64(gas),
            ctypes.byref(result),
        )
        return result

    def validate_transaction(
        self,
        to_address: str,
        value_eth: float = 0.0,
        gas_limit: int = 100000,
        calldata_hex: str = "0x",
        value_wei: int | None = None,
    ) -> ValidationSummary:
        """High-level validation with latency profiling. Never raises for bad agent input;
        malformed arguments produce an ``is_valid=False`` summary instead."""
        t0 = time.perf_counter_ns()

        def rejected(code: SentinelStatusCode, err: Exception) -> ValidationSummary:
            return ValidationSummary(
                is_valid=False,
                status_code=int(code),
                status_name=code.name,
                reason=f"Invalid input: {err}",
                function_selector="0x00000000",
                gas_limit=gas_limit if isinstance(gas_limit, int) else 0,
                value_wei=value_wei if isinstance(value_wei, int) else 0,
                latency_us=round((time.perf_counter_ns() - t0) / 1000.0, 2),
            )

        try:
            calldata = _parse_calldata(calldata_hex)
        except ValueError as err:
            return rejected(SentinelStatusCode.ERR_MALFORMED_CALLDATA, err)
        try:
            wei = value_wei if value_wei is not None else _eth_to_wei(value_eth)
            raw = self.validate_tx(to_address, calldata, wei, gas_limit)
        except (TypeError, ValueError) as err:
            return rejected(SentinelStatusCode.ERR_INVALID_ARGUMENT, err)
        latency_us = round((time.perf_counter_ns() - t0) / 1000.0, 2)

        return ValidationSummary(
            is_valid=(raw.status_code == SentinelStatusCode.OK),
            status_code=raw.status_code,
            status_name=_status_name(raw.status_code),
            reason=raw.reason_str,
            function_selector=f"0x{raw.selector:08x}",
            gas_limit=gas_limit,
            value_wei=wei,
            latency_us=latency_us,
        )

    def cache_put_status(self, key: str, value: str, ttl_seconds: float = 0.0) -> SentinelStatusCode:
        """Store ``value`` under ``key``. ``ttl_seconds <= 0`` means no expiry."""
        if not math.isfinite(ttl_seconds):
            return SentinelStatusCode.ERR_INVALID_ARGUMENT
        expires_at = 0
        if ttl_seconds > 0:
            expires_at = min(time.monotonic_ns() + int(ttl_seconds * 1e9), UINT64_MAX)
        with self._lock:
            if not self.is_initialized:
                return SentinelStatusCode.ERR_NOT_INITIALIZED
            rc = self._lib.sentinel_cache_put(
                ctypes.byref(self._arena),
                key.encode("utf-8"),
                value.encode("utf-8"),
                ctypes.c_uint64(expires_at),
            )
        return SentinelStatusCode(rc)

    def cache_put(self, key: str, value: str, ttl_seconds: float = 0.0) -> bool:
        return self.cache_put_status(key, value, ttl_seconds) == SentinelStatusCode.OK

    def cache_get(self, key: str) -> str | None:
        buf = ctypes.create_string_buffer(MAX_VAL_LEN)
        with self._lock:
            if not self.is_initialized:
                return None
            rc = self._lib.sentinel_cache_get(
                ctypes.byref(self._arena),
                key.encode("utf-8"),
                ctypes.c_uint64(time.monotonic_ns()),
                buf,
                ctypes.c_size_t(MAX_VAL_LEN),
            )
        if rc == SentinelStatusCode.OK:
            return buf.value.decode("utf-8", errors="replace")
        return None

    def cache_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "capacity": CACHE_CAPACITY,
                "count": self._arena.count,
                "next_idx": self._arena.next_idx,
                "is_initialized": bool(self._arena.is_initialized),
                "max_key_bytes": MAX_KEY_LEN - 1,
                "max_value_bytes": MAX_VAL_LEN - 1,
            }


_GLOBAL_BRIDGE: SentinelBridge | None = None
_GLOBAL_LOCK = threading.Lock()


def get_bridge() -> SentinelBridge:
    """Process-wide bridge singleton (lazily loaded)."""
    global _GLOBAL_BRIDGE
    with _GLOBAL_LOCK:
        if _GLOBAL_BRIDGE is None:
            _GLOBAL_BRIDGE = SentinelBridge()
        return _GLOBAL_BRIDGE
