"""Stateful Agent Guard & Spend Limiter.

Enforces financial session spend caps, single transaction ceilings, token-bucket
rate limiting, and address filtering before any Web3 transaction execution.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Set, Dict, Any, List


class GuardStatusCode(enum.IntEnum):
    OK = 0
    EXCEEDS_SINGLE_LIMIT = 1
    EXCEEDS_SESSION_LIMIT = 2
    RATE_LIMITED = 3
    BLACKLISTED_RECIPIENT = 4
    NOT_WHITELISTED = 5


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


class StatefulAgentGuard:
    """Thread-safe stateful budget guard and token-bucket rate limiter."""

    def __init__(self, config: GuardConfig | None = None) -> None:
        self.config = config or GuardConfig()
        self._session_spend_wei: int = 0
        self._recorded_txs: List[Dict[str, Any]] = []

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

    def check_transaction(self, target_address: str, value_wei: int) -> GuardCheckResult:
        """Validate whether a prospective transaction satisfies guard invariants."""
        # 1. Token-bucket rate limit check
        self._refill_tokens()
        if self._tokens < 1.0:
            return GuardCheckResult(
                allowed=False,
                status_code=GuardStatusCode.RATE_LIMITED,
                reason="Rate limit exceeded: Token bucket exhausted",
                session_spend_wei=self._session_spend_wei,
                remaining_session_budget_wei=max(0, self.config.max_session_spend_wei - self._session_spend_wei),
            )
        self._tokens -= 1.0

        normalized_addr = target_address.lower()

        # 2. Blacklist verification
        if normalized_addr in {addr.lower() for addr in self.config.blacklist}:
            return GuardCheckResult(
                allowed=False,
                status_code=GuardStatusCode.BLACKLISTED_RECIPIENT,
                reason=f"Target address {target_address} is blacklisted",
                session_spend_wei=self._session_spend_wei,
                remaining_session_budget_wei=max(0, self.config.max_session_spend_wei - self._session_spend_wei),
            )

        # 3. Whitelist verification (if active)
        if self.config.whitelist:
            if normalized_addr not in {addr.lower() for addr in self.config.whitelist}:
                return GuardCheckResult(
                    allowed=False,
                    status_code=GuardStatusCode.NOT_WHITELISTED,
                    reason=f"Target address {target_address} is not present in whitelist",
                    session_spend_wei=self._session_spend_wei,
                    remaining_session_budget_wei=max(0, self.config.max_session_spend_wei - self._session_spend_wei),
                )

        # 4. Single transaction cap
        if value_wei > self.config.max_single_tx_wei:
            return GuardCheckResult(
                allowed=False,
                status_code=GuardStatusCode.EXCEEDS_SINGLE_LIMIT,
                reason=(
                    f"Transaction value ({value_wei} wei) exceeds single transaction limit "
                    f"({self.config.max_single_tx_wei} wei)"
                ),
                session_spend_wei=self._session_spend_wei,
                remaining_session_budget_wei=max(0, self.config.max_session_spend_wei - self._session_spend_wei),
            )

        # 5. Cumulative session budget cap
        projected_spend = self._session_spend_wei + value_wei
        if projected_spend > self.config.max_session_spend_wei:
            remaining = max(0, self.config.max_session_spend_wei - self._session_spend_wei)
            return GuardCheckResult(
                allowed=False,
                status_code=GuardStatusCode.EXCEEDS_SESSION_LIMIT,
                reason=(
                    f"Cumulative spend ({projected_spend} wei) exceeds session spend budget "
                    f"({self.config.max_session_spend_wei} wei)"
                ),
                session_spend_wei=self._session_spend_wei,
                remaining_session_budget_wei=remaining,
            )

        return GuardCheckResult(
            allowed=True,
            status_code=GuardStatusCode.OK,
            reason="Transaction passed all guard checks",
            session_spend_wei=self._session_spend_wei,
            remaining_session_budget_wei=self.config.max_session_spend_wei - projected_spend,
        )

    def record_transaction(self, tx_hash: str, value_wei: int) -> None:
        """Record an executed transaction and increment cumulative spend."""
        self._session_spend_wei += value_wei
        self._recorded_txs.append({
            "tx_hash": tx_hash,
            "value_wei": value_wei,
            "timestamp": time.time(),
        })

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic metrics of the current guard session."""
        remaining = max(0, self.config.max_session_spend_wei - self._session_spend_wei)
        return {
            "session_spend_wei": self._session_spend_wei,
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
        self._session_spend_wei = 0
        self._recorded_txs.clear()
        self._tokens = self._burst_limit
        self._last_update = time.monotonic()
