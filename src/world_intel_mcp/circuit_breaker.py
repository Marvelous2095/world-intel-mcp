"""Per-source circuit breaker for world-intel-mcp.

Tracks failures per data source. Trips after N consecutive failures,
blocks calls for a cooldown period, then allows a single probe.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("world-intel-mcp.circuit_breaker")


@dataclass
class _State:
    failures: int = 0
    last_failure: float = 0.0
    tripped_at: float = 0.0
    is_open: bool = False
    total_trips: int = 0
    total_successes: int = 0
    total_failures: int = 0


class CircuitBreaker:
    """Circuit breaker with configurable thresholds per source."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300.0,
        per_source_config: dict[str, dict] | None = None,
        cache: Any = None,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._per_source: dict[str, dict] = per_source_config or {}
        self.cache = cache
        self._states: dict[str, _State] = {}
        if self.cache is not None:
            self._load_from_cache()

    def _load_from_cache(self) -> None:
        """Load breaker states from cache DB if available."""
        if not self.cache or not hasattr(self.cache, "load_breaker_states"):
            return
        loaded = self.cache.load_breaker_states()
        for source, data in loaded.items():
            self._states[source] = _State(
                failures=data["failures"],
                last_failure=data["last_failure"],
                tripped_at=data["tripped_at"],
                is_open=data["is_open"],
                total_trips=data["total_trips"],
                total_successes=data["total_successes"],
                total_failures=data["total_failures"],
            )

    def _save_state(self, source: str) -> None:
        """Save state to cache DB if available."""
        if not self.cache or not hasattr(self.cache, "save_breaker_state"):
            return
        state = self._get(source)
        self.cache.save_breaker_state(
            source,
            {
                "failures": state.failures,
                "last_failure": state.last_failure,
                "tripped_at": state.tripped_at,
                "is_open": state.is_open,
                "total_trips": state.total_trips,
                "total_successes": state.total_successes,
                "total_failures": state.total_failures,
            },
        )

    def _get(self, source: str) -> _State:
        if not self._states and self.cache:
            self._load_from_cache()
        if source not in self._states:
            self._states[source] = _State()
        return self._states[source]

    def _threshold_for(self, source: str) -> int:
        """Get failure threshold for a specific source."""
        return self._per_source.get(source, {}).get("failure_threshold", self.failure_threshold)

    def _cooldown_for(self, source: str) -> float:
        """Get cooldown seconds for a specific source."""
        return self._per_source.get(source, {}).get("cooldown_seconds", self.cooldown_seconds)

    def is_available(self, source: str) -> bool:
        """Check if source is available (circuit closed or cooldown elapsed)."""
        state = self._get(source)
        if not state.is_open:
            return True
        if time.time() - state.tripped_at >= self._cooldown_for(source):
            return True  # allow probe
        return False

    def record_success(self, source: str) -> None:
        """Record successful call — resets failure count, closes circuit."""
        state = self._get(source)
        state.failures = 0
        state.is_open = False
        state.total_successes += 1
        self._save_state(source)

    def record_failure(self, source: str) -> None:
        """Record failed call — increments counter, may trip breaker."""
        state = self._get(source)
        state.failures += 1
        state.last_failure = time.time()
        state.total_failures += 1
        if state.failures >= self._threshold_for(source) and not state.is_open:
            state.is_open = True
            state.tripped_at = time.time()
            state.total_trips += 1
            logger.warning(
                "Circuit breaker TRIPPED for %s (failures=%d, cooldown=%.0fs)",
                source, state.failures, self._cooldown_for(source),
            )
        self._save_state(source)

    def status(self) -> dict[str, dict]:
        """Return status of all tracked sources."""
        now = time.time()
        result = {}
        for source, state in self._states.items():
            if state.is_open:
                remaining = max(0, self._cooldown_for(source) - (now - state.tripped_at))
                status = "open" if remaining > 0 else "half-open"
            else:
                remaining = 0
                status = "closed"
            result[source] = {
                "status": status,
                "failures": state.failures,
                "cooldown_remaining_s": round(remaining, 1),
                "total_trips": state.total_trips,
                "total_successes": state.total_successes,
                "total_failures": state.total_failures,
            }
        return result
