"""
Circuit Breaker Pattern for Fault Tolerance.

Prevents repeated calls to a failing source, allowing it time to recover.

States:
    CLOSED    → Normal operation. Requests go through.
    OPEN      → Source has failed too many times. Requests are blocked for a cooldown period.
    HALF_OPEN → After cooldown, ONE test request is allowed. If it succeeds → CLOSED. If it fails → OPEN.

Usage:
    breaker = breakers['amazon']
    if breaker.can_execute():
        try:
            result = call_service()
            breaker.record_success()
        except Exception:
            breaker.record_failure()
    else:
        # Source is down, skip it (fault tolerance!)
        result = []
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Circuit Breaker implementation for a single data source.

    - After `failure_threshold` consecutive failures → state becomes OPEN (blocks calls)
    - After `recovery_timeout` seconds → state becomes HALF_OPEN (allows one test call)
    - If test call succeeds → CLOSED again
    - If test call fails → OPEN again
    """

    CLOSED = 'CLOSED'
    OPEN = 'OPEN'
    HALF_OPEN = 'HALF_OPEN'

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = self.CLOSED
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check if a request is allowed through the breaker."""
        with self._lock:
            if self.state == self.CLOSED:
                return True

            elif self.state == self.OPEN:
                # Check if cooldown period has passed
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    logger.info(
                        f"⚡ Circuit [{self.name}] → HALF_OPEN (testing recovery after {elapsed:.0f}s)"
                    )
                    return True
                return False

            elif self.state == self.HALF_OPEN:
                return True

            return False

    def record_success(self):
        """Record a successful call. Resets the breaker to CLOSED."""
        with self._lock:
            prev_state = self.state
            self.failure_count = 0
            self.state = self.CLOSED
            if prev_state != self.CLOSED:
                logger.info(f"✅ Circuit [{self.name}] → CLOSED (recovered)")

    def record_failure(self):
        """Record a failed call. May trip the breaker to OPEN."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == self.HALF_OPEN:
                # Test call failed, go back to OPEN
                self.state = self.OPEN
                logger.warning(f"🔴 Circuit [{self.name}] → OPEN (recovery test failed)")

            elif self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                logger.warning(
                    f"🔴 Circuit [{self.name}] → OPEN "
                    f"(failed {self.failure_count} times, blocking for {self.recovery_timeout}s)"
                )

    def get_status(self) -> dict:
        """Return current breaker status as a dict."""
        return {
            'source': self.name,
            'state': self.state,
            'failure_count': self.failure_count,
            'threshold': self.failure_threshold,
        }


# ─── Global Circuit Breakers (one per data source) ───────────────────────────

breakers = {
    'amazon':  CircuitBreaker('Amazon',  failure_threshold=5, recovery_timeout=60),
    'ebay':    CircuitBreaker('eBay',    failure_threshold=5, recovery_timeout=60),
    'google':  CircuitBreaker('Google',  failure_threshold=5, recovery_timeout=60),
    'walmart': CircuitBreaker('Walmart', failure_threshold=5, recovery_timeout=60),
}
