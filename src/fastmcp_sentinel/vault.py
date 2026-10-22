"""Minimal, dependency-free client for the on-chain ``SentinelVault`` contract.

The vault (``contracts/src/SentinelVault.sol``) holds an agent's USDC and enforces
spend policy on-chain. This module ABI-encodes the handful of calls the MCP server
needs. Function selectors are pinned here and verified against the Foundry build
artifact in ``tests/test_vault.py``.
"""

from __future__ import annotations

import enum
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

USDC_DECIMALS = 6

SELECTORS: Dict[str, str] = {
    "check(address,uint256)": "96fb7217",
    "pay(address,uint256,bytes32)": "5e5571ac",
    "policy()": "0505c8c9",
    "balanceOf(address)": "70a08231",
}

# Custom errors, so reverts from the vault decode to readable names.
VAULT_ERRORS: Dict[str, str] = {
    "e773e0a9": "InvalidLimits()",
    "c1ab6dc1": "InvalidToken()",
    "0d9ab13f": "NotAgent()",
    "30cd7471": "NotOwner()",
    "1853971c": "NotPendingOwner()",
    "3fb1d2b1": "PaymentRejected(uint8)",
    "ab143c06": "Reentrancy()",
    "90b8ec18": "TransferFailed()",
    "d92e233d": "ZeroAddress()",
}

PAYMENT_EVENT_TOPIC = "0xabcefd63f1c3fa546491ac11efb08637a655ec1410d76875df7f453253a49d08"

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class VaultStatus(enum.IntEnum):
    """Mirror of ``SentinelVault.Status``."""

    OK = 0
    PAUSED = 1
    INVALID_RECIPIENT = 2
    INVALID_AMOUNT = 3
    EXCEEDS_SINGLE_LIMIT = 4
    EXCEEDS_PERIOD_LIMIT = 5
    NOT_ALLOWLISTED = 6
    INSUFFICIENT_BALANCE = 7


@dataclass
class VaultPolicy:
    owner: str
    agent: str
    token: str
    max_per_tx: int
    max_per_period: int
    period_seconds: int
    period_start: int
    spent_in_period: int
    allowlist_enabled: bool
    paused: bool
    balance: int

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("max_per_tx", "max_per_period", "spent_in_period", "balance"):
            d[f"{k}_usdc"] = format_usdc(d[k])
        d["remaining_in_period"] = max(0, self.max_per_period - self.spent_in_period)
        d["remaining_in_period_usdc"] = format_usdc(d["remaining_in_period"])
        return d


# --- encoding -----------------------------------------------------------------


def require_address(value: str, field: str = "address") -> str:
    if not isinstance(value, str) or not _ADDRESS_RE.match(value):
        raise ValueError(f"{field} must be a 0x-prefixed 20-byte hex address (got {value!r})")
    return value


def _word_address(addr: str) -> str:
    return require_address(addr)[2:].lower().rjust(64, "0")


def _word_uint(value: int, bits: int = 256) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 2**bits:
        raise ValueError(f"value out of range for uint{bits}: {value!r}")
    return format(value, "064x")


def encode_memo(memo: str) -> str:
    """``0x`` + 64 hex chars is used verbatim; otherwise UTF-8 text (<= 32 bytes) is right-padded."""
    if re.fullmatch(r"0x[0-9a-fA-F]{64}", memo or ""):
        return memo[2:].lower()
    raw = (memo or "").encode("utf-8")
    if len(raw) > 32:
        raise ValueError("memo must be <= 32 bytes of UTF-8 or a 0x-prefixed 32-byte hex string")
    return raw.hex().ljust(64, "0")


def encode_check(to: str, amount: int) -> str:
    return "0x" + SELECTORS["check(address,uint256)"] + _word_address(to) + _word_uint(amount)


def encode_pay(to: str, amount: int, memo: str = "") -> str:
    return "0x" + SELECTORS["pay(address,uint256,bytes32)"] + _word_address(to) + _word_uint(amount) + encode_memo(memo)


def encode_policy() -> str:
    return "0x" + SELECTORS["policy()"]


def encode_balance_of(owner: str) -> str:
    return "0x" + SELECTORS["balanceOf(address)"] + _word_address(owner)


# --- decoding -----------------------------------------------------------------


def _words(hex_data: str, expected: int) -> List[int]:
    data = hex_data[2:] if hex_data.startswith(("0x", "0X")) else hex_data
    if len(data) < expected * 64:
        raise ValueError(f"return data too short: expected {expected} words, got {len(data) // 64}")
    return [int(data[i * 64 : (i + 1) * 64], 16) for i in range(expected)]


def _as_address(word: int) -> str:
    return "0x" + format(word, "040x")[-40:]


def decode_policy(hex_data: str) -> VaultPolicy:
    w = _words(hex_data, 11)
    return VaultPolicy(
        owner=_as_address(w[0]),
        agent=_as_address(w[1]),
        token=_as_address(w[2]),
        max_per_tx=w[3],
        max_per_period=w[4],
        period_seconds=w[5],
        period_start=w[6],
        spent_in_period=w[7],
        allowlist_enabled=bool(w[8]),
        paused=bool(w[9]),
        balance=w[10],
    )


def decode_check(hex_data: str) -> Tuple[VaultStatus, int]:
    status, remaining = _words(hex_data, 2)
    return VaultStatus(status), remaining


def decode_vault_error(hex_data: str) -> str | None:
    data = (hex_data or "").lower().removeprefix("0x")
    name = VAULT_ERRORS.get(data[:8])
    if name is None:
        return None
    if name == "PaymentRejected(uint8)" and len(data) >= 72:
        try:
            return f"PaymentRejected({VaultStatus(int(data[8:72], 16)).name})"
        except ValueError:
            return name
    return name


# --- amounts ------------------------------------------------------------------


def parse_usdc(amount: str | int | float) -> int:
    """Exact human USDC -> 6-decimal base units. Rejects negatives and sub-micro precision."""
    try:
        dec = Decimal(str(amount).strip())
    except InvalidOperation as err:
        raise ValueError(f"amount_usdc is not a number: {amount!r}") from err
    if not dec.is_finite() or dec <= 0:
        raise ValueError("amount_usdc must be a positive finite number")
    units = dec * 10**USDC_DECIMALS
    if units != units.to_integral_value():
        raise ValueError("amount_usdc has more than 6 decimal places")
    return int(units)


def format_usdc(units: int) -> str:
    return f"{Decimal(units) / 10**USDC_DECIMALS:.6f}"
