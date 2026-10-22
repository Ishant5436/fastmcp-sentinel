"""Stateful Agent Guard & Spend Limiter.

Enforces financial session spend caps, single transaction ceilings, token-bucket
rate limiting, and address filtering before any Web3 transaction execution.
"""

from __future__ import annotations

import enum
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_valid_address(address: str) -> bool:
    return isinstance(address, str) and bool(_ADDRESS_RE.match(address))


class GuardStatusCode(enum.IntEnum):
    OK = 0
    EXCEEDS_SINGLE_LIMIT = 1
    EXCEEDS_SESSION_LIMIT = 2
    RATE_LIMITED = 3
    BLACKLISTED_RECIPIENT = 4
    NOT_WHITELISTED = 5
    INVALID_ADDRESS = 6
    INVALID_VALUE = 7


@dataclass
class GuardCheckResult:
    allowed: bool
    status_code: GuardStatusCode
    reason: str
    session_spend_wei: int
    remaining_session_budget_wei: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status_code": int(self.status_code),
            "status_name": self.status_code.name,
            "reason": self.reason,
            "session_spend_wei": self.session_spend_wei,
            "remaining_session_budget_wei": self.remaining_session_budget_wei,
        }


@dataclass
class GuardConfig:
    max_single_tx_wei: int = 10**18  # 1 ETH default
    max_session_spend_wei: int = 5 * 10**18  # 5 ETH default
    rate_limit_per_minute: int = 60
    burst_limit: int = 10
    blacklist: Set[str] = field(default_factory=set)
    whitelist: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.max_single_tx_wei < 0 or self.max_session_spend_wei < 0:
            raise ValueError("spend limits must be non-negative")
        if self.rate_limit_per_minute <= 0 or self.burst_limit <= 0:
            raise ValueError("rate_limit_per_minute and burst_limit must be positive")


class StatefulAgentGuard:
    """Thread-safe stateful budget guard and token-bucket rate limiter."""

    def __init__(self, config: GuardConfig | None = None) -> None:
        self.config = config or GuardConfig()
        self._lock = threading.RLock()
        self._blacklist = frozenset(a.lower() for a in self.config.blacklist)
        self._whitelist = frozenset(a.lower() for a in self.config.whitelist)
        self._session_spend_wei: int = 0
        self._recorded_txs: List[Dict[str, Any]] = []

        # Token-bucket state
        self._burst_limit = float(self.config.burst_limit)
        self._tokens = float(self.config.burst_limit)
        self._fill_rate = self.config.rate_limit_per_minute / 60.0
        self._last_update = time.monotonic()

    def _remaining(self) -> int:
        return max(0, self.config.max_session_spend_wei - self._session_spend_wei)

    def _refill_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now
        self._tokens = min(self._burst_limit, self._tokens + elapsed * self._fill_rate)

    def _deny(self, code: GuardStatusCode, reason: str) -> GuardCheckResult:
        return GuardCheckResult(
            allowed=False,
            status_code=code,
            reason=reason,
            session_spend_wei=self._session_spend_wei,
            remaining_session_budget_wei=self._remaining(),
        )

    def _evaluate(self, target_address: str, value_wei: int) -> GuardCheckResult:
        # 1. Input validation (before consuming a rate-limit token)
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            return self._deny(GuardStatusCode.INVALID_VALUE, "Transaction value must be a non-negative integer (wei)")
        if not is_valid_address(target_address):
            return self._deny(
                GuardStatusCode.INVALID_ADDRESS,
                f"Target address {target_address!r} is not a 0x-prefixed 20-byte hex address",
            )

        # 2. Token-bucket rate limit check
        self._refill_tokens()
        if self._tokens < 1.0:
            return self._deny(GuardStatusCode.RATE_LIMITED, "Rate limit exceeded: Token bucket exhausted")
        self._tokens -= 1.0

        normalized_addr = target_address.lower()

        # 3. Blacklist verification
        if normalized_addr in self._blacklist:
            return self._deny(GuardStatusCode.BLACKLISTED_RECIPIENT, f"Target address {target_address} is blacklisted")

        # 4. Whitelist verification (if active)
        if self._whitelist and normalized_addr not in self._whitelist:
            return self._deny(
                GuardStatusCode.NOT_WHITELISTED, f"Target address {target_address} is not present in whitelist"
            )

        # 5. Single transaction cap
        if value_wei > self.config.max_single_tx_wei:
            return self._deny(
                GuardStatusCode.EXCEEDS_SINGLE_LIMIT,
                f"Transaction value ({value_wei} wei) exceeds single transaction limit "
                f"({self.config.max_single_tx_wei} wei)",
            )

        # 6. Cumulative session budget cap
        projected_spend = self._session_spend_wei + value_wei
        if projected_spend > self.config.max_session_spend_wei:
            return self._deny(
                GuardStatusCode.EXCEEDS_SESSION_LIMIT,
                f"Cumulative spend ({projected_spend} wei) exceeds session spend budget "
                f"({self.config.max_session_spend_wei} wei)",
            )

        return GuardCheckResult(
            allowed=True,
            status_code=GuardStatusCode.OK,
            reason="Transaction passed all guard checks",
            session_spend_wei=self._session_spend_wei,
            remaining_session_budget_wei=self.config.max_session_spend_wei - projected_spend,
        )

    def check_transaction(self, target_address: str, value_wei: int) -> GuardCheckResult:
        """Validate whether a prospective transaction satisfies guard invariants.

        Does not reserve budget; prefer :meth:`authorize` to avoid check/record races.
        """
        with self._lock:
            result = self._evaluate(target_address, value_wei)
        logger.info(
            "guard.check target=%s value_wei=%s allowed=%s status=%s",
            target_address,
            value_wei,
            result.allowed,
            result.status_code.name,
        )
        return result

    def authorize(self, target_address: str, value_wei: int, tx_ref: str = "") -> GuardCheckResult:
        """Atomically check a transaction and, if allowed, reserve its value against the budget."""
        with self._lock:
            result = self._evaluate(target_address, value_wei)
            if result.allowed:
                self._record_locked(tx_ref, value_wei, target_address)
                result.session_spend_wei = self._session_spend_wei
        logger.info(
            "guard.authorize target=%s value_wei=%s allowed=%s status=%s",
            target_address,
            value_wei,
            result.allowed,
            result.status_code.name,
        )
        return result

    def _record_locked(self, tx_hash: str, value_wei: int, target_address: str = "") -> None:
        self._session_spend_wei += value_wei
        self._recorded_txs.append(
            {
                "tx_hash": tx_hash,
                "to": target_address,
                "value_wei": value_wei,
                "timestamp": time.time(),
            }
        )

    def record_transaction(self, tx_hash: str, value_wei: int) -> None:
        """Record an executed transaction and increment cumulative spend."""
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            raise ValueError("value_wei must be a non-negative integer")
        with self._lock:
            self._record_locked(tx_hash, value_wei)
        logger.info("guard.record tx_hash=%s value_wei=%s", tx_hash, value_wei)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic metrics of the current guard session."""
        with self._lock:
            self._refill_tokens()
            return {
                "session_spend_wei": self._session_spend_wei,
                "max_session_spend_wei": self.config.max_session_spend_wei,
                "remaining_session_budget_wei": self._remaining(),
                "max_single_tx_wei": self.config.max_single_tx_wei,
                "transactions_recorded": len(self._recorded_txs),
                "tokens_available": round(self._tokens, 2),
                "whitelist_count": len(self._whitelist),
                "blacklist_count": len(self._blacklist),
            }

    def reset_session(self) -> None:
        """Reset session cumulative spend."""
        with self._lock:
            self._session_spend_wei = 0
            self._recorded_txs.clear()
            self._tokens = self._burst_limit
            self._last_update = time.monotonic()
        logger.warning("guard.reset session spend cleared")
