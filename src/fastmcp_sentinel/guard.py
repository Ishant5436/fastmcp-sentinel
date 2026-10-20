"""Stateful Agent Guard & Spend Limiter.

Enforces financial session spend caps, single transaction ceilings, token-bucket
rate limiting, and address filtering before any Web3 transaction execution.

Spend is binding through reservations: `reserve_transaction` counts the value against the
session budget at approval time, so an agent that never reports back still cannot exceed
the cap. `confirm_reservation` finalizes it with a tx hash; `release_reservation` refunds it
only if the transaction was never broadcast.
"""

from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Set, Dict, Any, List, Optional, Tuple


class GuardStatusCode(enum.IntEnum):
    OK = 0
    EXCEEDS_SINGLE_LIMIT = 1
    EXCEEDS_SESSION_LIMIT = 2
    RATE_LIMITED = 3
    BLACKLISTED_RECIPIENT = 4
    NOT_WHITELISTED = 5
    INVALID_VALUE = 6


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
    max_single_tx_wei: int = 10**18  # 1 native unit default
    max_session_spend_wei: int = 5 * 10**18  # 5 native units default
    rate_limit_per_minute: int = 60
    burst_limit: int = 10
    blacklist: Set[str] = field(default_factory=set)
    whitelist: Set[str] = field(default_factory=set)


class StatefulAgentGuard:
    """Thread-safe stateful budget guard and token-bucket rate limiter."""

    def __init__(self, config: GuardConfig | None = None) -> None:
        self.config = config or GuardConfig()
        self._session_spend_wei: int = 0
        self._reservations: Dict[str, int] = {}
        self._recorded_txs: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        # Token-bucket state
        self._burst_limit = float(self.config.burst_limit)
        self._tokens = float(self.config.burst_limit)
        self._fill_rate = self.config.rate_limit_per_minute / 60.0
        self._last_update = time.monotonic()

    def _refill_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now
        self._tokens = min(self._burst_limit, self._tokens + elapsed * self._fill_rate)

    def _spend_including_reserved(self) -> int:
        return self._session_spend_wei + sum(self._reservations.values())

    def check_transaction(self, target_address: str, value_wei: int) -> GuardCheckResult:
        """Validate whether a prospective transaction satisfies guard invariants.

        This is advisory only: nothing is held against the budget. Use
        `reserve_transaction` when the agent intends to broadcast.
        """
        with self._lock:
            return self._evaluate(target_address, value_wei)

    def reserve_transaction(
        self, target_address: str, value_wei: int
    ) -> Tuple[GuardCheckResult, Optional[str]]:
        """Check a transaction and, if allowed, hold its value against the session budget.

        Returns the check result and a reservation id (None when the transaction is refused).
        """
        with self._lock:
            result = self._evaluate(target_address, value_wei)
            if not result.allowed:
                return result, None
            reservation_id = uuid.uuid4().hex
            self._reservations[reservation_id] = value_wei
            result.session_spend_wei = self._spend_including_reserved()
            return result, reservation_id

    def confirm_reservation(self, reservation_id: str, tx_hash: str) -> bool:
        """Finalize a reservation once its transaction has been broadcast."""
        with self._lock:
            value_wei = self._reservations.pop(reservation_id, None)
            if value_wei is None:
                return False
            self._commit(tx_hash, value_wei)
            return True

    def release_reservation(self, reservation_id: str) -> bool:
        """Refund a reservation whose transaction was never broadcast."""
        with self._lock:
            return self._reservations.pop(reservation_id, None) is not None

    def _evaluate(self, target_address: str, value_wei: int) -> GuardCheckResult:
        session_spend = self._spend_including_reserved()
        remaining = max(0, self.config.max_session_spend_wei - session_spend)

        def refuse(code: GuardStatusCode, reason: str) -> GuardCheckResult:
            return GuardCheckResult(
                allowed=False,
                status_code=code,
                reason=reason,
                session_spend_wei=session_spend,
                remaining_session_budget_wei=remaining,
            )

        # 0. Malformed values (negative amounts would otherwise refill the budget)
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            return refuse(
                GuardStatusCode.INVALID_VALUE,
                f"Transaction value must be a non-negative integer (got {value_wei!r})",
            )

        # 1. Token-bucket rate limit check
        self._refill_tokens()
        if self._tokens < 1.0:
            return refuse(GuardStatusCode.RATE_LIMITED, "Rate limit exceeded: Token bucket exhausted")
        self._tokens -= 1.0

        normalized_addr = target_address.lower()

        # 2. Blacklist verification
        if normalized_addr in {addr.lower() for addr in self.config.blacklist}:
            return refuse(
                GuardStatusCode.BLACKLISTED_RECIPIENT,
                f"Target address {target_address} is blacklisted",
            )

        # 3. Whitelist verification (if active)
        if self.config.whitelist:
            if normalized_addr not in {addr.lower() for addr in self.config.whitelist}:
                return refuse(
                    GuardStatusCode.NOT_WHITELISTED,
                    f"Target address {target_address} is not present in whitelist",
                )

        # 4. Single transaction cap
        if value_wei > self.config.max_single_tx_wei:
            return refuse(
                GuardStatusCode.EXCEEDS_SINGLE_LIMIT,
                f"Transaction value ({value_wei} wei) exceeds single transaction limit "
                f"({self.config.max_single_tx_wei} wei)",
            )

        # 5. Cumulative session budget cap (committed spend plus open reservations)
        projected_spend = session_spend + value_wei
        if projected_spend > self.config.max_session_spend_wei:
            return refuse(
                GuardStatusCode.EXCEEDS_SESSION_LIMIT,
                f"Cumulative spend ({projected_spend} wei) exceeds session spend budget "
                f"({self.config.max_session_spend_wei} wei)",
            )

        return GuardCheckResult(
            allowed=True,
            status_code=GuardStatusCode.OK,
            reason="Transaction passed all guard checks",
            session_spend_wei=session_spend,
            remaining_session_budget_wei=self.config.max_session_spend_wei - projected_spend,
        )

    def record_transaction(self, tx_hash: str, value_wei: int) -> None:
        """Record an executed transaction and increment cumulative spend."""
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            raise ValueError(f"value_wei must be a non-negative integer (got {value_wei!r})")
        with self._lock:
            self._commit(tx_hash, value_wei)

    def _commit(self, tx_hash: str, value_wei: int) -> None:
        self._session_spend_wei += value_wei
        self._recorded_txs.append({
            "tx_hash": tx_hash,
            "value_wei": value_wei,
            "timestamp": time.time(),
        })

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic metrics of the current guard session."""
        with self._lock:
            reserved = sum(self._reservations.values())
            remaining = max(0, self.config.max_session_spend_wei - self._session_spend_wei - reserved)
            return {
                "session_spend_wei": self._session_spend_wei,
                "reserved_wei": reserved,
                "pending_reservations": len(self._reservations),
                "max_session_spend_wei": self.config.max_session_spend_wei,
                "remaining_session_budget_wei": remaining,
                "max_single_tx_wei": self.config.max_single_tx_wei,
                "transactions_recorded": len(self._recorded_txs),
                "tokens_available": round(self._tokens, 2),
                "whitelist_count": len(self.config.whitelist),
                "blacklist_count": len(self.config.blacklist),
            }

    def reset_session(self) -> None:
        """Reset session cumulative spend."""
        with self._lock:
            self._session_spend_wei = 0
            self._reservations.clear()
            self._recorded_txs.clear()
            self._tokens = self._burst_limit
            self._last_update = time.monotonic()
