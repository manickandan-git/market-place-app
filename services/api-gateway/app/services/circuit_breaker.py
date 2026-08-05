import time
from dataclasses import dataclass, field


@dataclass
class _State:
    consecutive_failures: int = 0
    opened_at: float | None = None


@dataclass
class CircuitBreaker:
    """Per-key (per-upstream) fail-fast breaker.

    Without this, a downstream service that's hard down still gets hit on
    every single proxied request and each one waits out the full
    `downstream_timeout_seconds` before failing — slow for callers and
    wasted load on a service that's already struggling. After
    `failure_threshold` consecutive failures for a given key, the circuit
    opens: calls fail immediately with no network attempt for
    `cooldown_seconds`. After that, the next call is let through as a
    trial (half-open) — a success closes the circuit again, a failure
    reopens it and restarts the cooldown.

    Not thread-safe in the OS-thread sense, but that's fine: this only
    ever runs inside a single asyncio event loop, and none of these
    methods await, so there's no interleaving point for another task to
    observe inconsistent state mid-update.
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    _states: dict[str, _State] = field(default_factory=dict)

    def _state(self, key: str) -> _State:
        return self._states.setdefault(key, _State())

    def is_open(self, key: str) -> bool:
        state = self._state(key)
        if state.opened_at is None:
            return False
        if time.monotonic() - state.opened_at >= self.cooldown_seconds:
            return False  # cooldown elapsed: let the next call through as a trial
        return True

    def record_success(self, key: str) -> None:
        state = self._state(key)
        state.consecutive_failures = 0
        state.opened_at = None

    def record_failure(self, key: str) -> None:
        state = self._state(key)
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.failure_threshold:
            # Re-stamped on every qualifying failure, not just the first —
            # a half-open trial that fails again must restart the full
            # cooldown, not fall back to the original open timestamp.
            state.opened_at = time.monotonic()
