import time

from app.services.circuit_breaker import CircuitBreaker


def test_closed_by_default():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    assert breaker.is_open("product") is False


def test_stays_closed_below_threshold():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    breaker.record_failure("product")
    breaker.record_failure("product")
    assert breaker.is_open("product") is False


def test_opens_after_threshold_consecutive_failures():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    for _ in range(3):
        breaker.record_failure("product")
    assert breaker.is_open("product") is True


def test_success_resets_failure_count():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    breaker.record_failure("product")
    breaker.record_failure("product")
    breaker.record_success("product")
    breaker.record_failure("product")
    breaker.record_failure("product")
    assert breaker.is_open("product") is False


def test_half_opens_after_cooldown_elapses():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    breaker.record_failure("product")
    breaker.record_failure("product")
    assert breaker.is_open("product") is True
    time.sleep(0.08)
    assert breaker.is_open("product") is False


def test_failed_half_open_trial_restarts_cooldown():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    breaker.record_failure("product")
    breaker.record_failure("product")
    time.sleep(0.08)
    assert breaker.is_open("product") is False  # trial allowed through
    breaker.record_failure("product")  # trial fails
    assert breaker.is_open("product") is True  # reopened, fresh cooldown
    time.sleep(0.08)
    assert breaker.is_open("product") is False  # cooldown elapsed again


def test_successful_half_open_trial_closes_circuit():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    breaker.record_failure("product")
    breaker.record_failure("product")
    time.sleep(0.08)
    breaker.record_success("product")
    breaker.record_failure("product")
    assert breaker.is_open("product") is False  # only 1 consecutive since reset


def test_breakers_are_independent_per_key():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    breaker.record_failure("product")
    assert breaker.is_open("product") is True
    assert breaker.is_open("inventory") is False
