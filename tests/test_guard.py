import pytest
import time
from fastmcp_sentinel.guard import (
    StatefulAgentGuard,
    GuardConfig,
    GuardCheckResult,
    GuardStatusCode,
)

def test_single_tx_limit_enforcement():
    # 1 ETH limit for single tx, 5 ETH for session
    config = GuardConfig(
        max_single_tx_wei=10**18,
        max_session_spend_wei=5 * 10**18,
        rate_limit_per_minute=60,
        burst_limit=10,
    )
    guard = StatefulAgentGuard(config)

    # Valid transaction: 0.5 ETH
    res1 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=5 * 10**17)
    assert res1.allowed is True
    assert res1.status_code == GuardStatusCode.OK

    # Excessive single transaction: 1.5 ETH > 1.0 ETH
    res2 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=15 * 10**17)
    assert res2.allowed is False
    assert res2.status_code == GuardStatusCode.EXCEEDS_SINGLE_LIMIT
    assert "exceeds single transaction limit" in res2.reason

def test_cumulative_session_spend_enforcement():
    config = GuardConfig(
        max_single_tx_wei=10**18,
        max_session_spend_wei=2 * 10**18,
        rate_limit_per_minute=60,
        burst_limit=10,
    )
    guard = StatefulAgentGuard(config)

    # First tx: 0.8 ETH
    res1 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=8 * 10**17)
    assert res1.allowed is True
    guard.record_transaction(tx_hash="0xabc1", value_wei=8 * 10**17)

    # Second tx: 0.8 ETH (Cumulative = 1.6 ETH <= 2.0 ETH)
    res2 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=8 * 10**17)
    assert res2.allowed is True
    guard.record_transaction(tx_hash="0xabc2", value_wei=8 * 10**17)

    # Third tx: 0.8 ETH (Cumulative would be 2.4 ETH > 2.0 ETH)
    res3 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=8 * 10**17)
    assert res3.allowed is False
    assert res3.status_code == GuardStatusCode.EXCEEDS_SESSION_LIMIT
    assert "exceeds session spend budget" in res3.reason
    assert res3.remaining_session_budget_wei == 4 * 10**17

def test_token_bucket_rate_limiting():
    config = GuardConfig(
        max_single_tx_wei=10**18,
        max_session_spend_wei=10 * 10**18,
        rate_limit_per_minute=60,  # 1 token / sec
        burst_limit=2,
    )
    guard = StatefulAgentGuard(config)

    # Consuming 2 burst tokens immediately
    res1 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=0)
    assert res1.allowed is True
    res2 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=0)
    assert res2.allowed is True

    # 3rd rapid check should trigger rate limiting
    res3 = guard.check_transaction(target_address="0x1111111111111111111111111111111111111111", value_wei=0)
    assert res3.allowed is False
    assert res3.status_code == GuardStatusCode.RATE_LIMITED
    assert "Rate limit exceeded" in res3.reason

def test_address_filtering():
    blacklisted = "0xBadBadBadBadBadBadBadBadBadBadBadBadBadB"
    whitelisted = "0xGoodGoodGoodGoodGoodGoodGoodGoodGoodGood"

    config = GuardConfig(
        max_single_tx_wei=10**18,
        max_session_spend_wei=10 * 10**18,
        blacklist={blacklisted.lower()},
        whitelist={whitelisted.lower()},
    )
    guard = StatefulAgentGuard(config)

    # Blacklisted address
    res_b = guard.check_transaction(target_address=blacklisted, value_wei=0)
    assert res_b.allowed is False
    assert res_b.status_code == GuardStatusCode.BLACKLISTED_RECIPIENT

    # Non-whitelisted address
    res_unknown = guard.check_transaction(target_address="0x2222222222222222222222222222222222222222", value_wei=0)
    assert res_unknown.allowed is False
    assert res_unknown.status_code == GuardStatusCode.NOT_WHITELISTED

    # Whitelisted address
    res_w = guard.check_transaction(target_address=whitelisted, value_wei=0)
    assert res_w.allowed is True
    assert res_w.status_code == GuardStatusCode.OK


def test_negative_values_rejected():
    guard = StatefulAgentGuard(GuardConfig(max_single_tx_wei=10**18, max_session_spend_wei=2 * 10**18))
    res = guard.check_transaction("0x1111111111111111111111111111111111111111", value_wei=-10**18)
    assert res.allowed is False
    assert res.status_code == GuardStatusCode.INVALID_VALUE
    with pytest.raises(ValueError):
        guard.record_transaction("0xbad", -5 * 10**18)
    assert guard.get_status()["session_spend_wei"] == 0


def test_reservations_count_against_budget():
    guard = StatefulAgentGuard(GuardConfig(max_single_tx_wei=10**18, max_session_spend_wei=15 * 10**17))
    to = "0x1111111111111111111111111111111111111111"
    res1, rid1 = guard.reserve_transaction(to, 10**18)
    assert res1.allowed and rid1
    # Second reservation would exceed 1.5 even though nothing was "recorded"
    res2, rid2 = guard.reserve_transaction(to, 10**18)
    assert res2.allowed is False and rid2 is None
    assert res2.status_code == GuardStatusCode.EXCEEDS_SESSION_LIMIT

    assert guard.release_reservation(rid1) is True
    assert guard.release_reservation(rid1) is False
    res3, rid3 = guard.reserve_transaction(to, 10**18)
    assert res3.allowed
    assert guard.confirm_reservation(rid3, "0xfeed") is True
    status = guard.get_status()
    assert status["session_spend_wei"] == 10**18
    assert status["transactions_recorded"] == 1
    assert status["reserved_wei"] == 0


def test_concurrent_reservations_never_exceed_budget():
    import threading

    guard = StatefulAgentGuard(
        GuardConfig(max_single_tx_wei=10**18, max_session_spend_wei=5 * 10**18, burst_limit=1000, rate_limit_per_minute=60000)
    )
    granted = []

    def worker():
        res, rid = guard.reserve_transaction("0x1111111111111111111111111111111111111111", 10**18)
        if rid:
            granted.append(rid)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 5
    assert guard.get_status()["reserved_wei"] == 5 * 10**18
