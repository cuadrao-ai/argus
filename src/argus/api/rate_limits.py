from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class InFlightGate:
    """Requests in flight per key, capped. The caller releases what it took."""

    def __init__(self) -> None:
        self._active: defaultdict[str, int] = defaultdict(int)
        self._lock = Lock()

    def take(self, key: str, *, limit: int) -> bool:
        with self._lock:
            if self._active[key] >= limit:
                return False
            self._active[key] += 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            if self._active[key] <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] -= 1

    def reset(self) -> None:
        with self._lock:
            self._active.clear()


class SlidingWindowLimiter:
    """Small bounded in-process limiter for authenticated API edge controls."""

    def __init__(self, *, compact_threshold: int = 2048) -> None:
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._compact_threshold = compact_threshold

    def record_or_retry_after(
        self,
        *,
        keys: tuple[str, ...],
        limit: int,
        window_seconds: int,
    ) -> int | None:
        now = monotonic()
        with self._lock:
            if len(self._attempts) >= self._compact_threshold:
                self._compact(now=now, window_seconds=window_seconds)
            retry_after = 0
            for key in keys:
                attempts = self._attempts[key]
                self._prune(attempts, now=now, window_seconds=window_seconds)
                if len(attempts) >= limit:
                    retry_after = max(
                        retry_after,
                        int(window_seconds - (now - attempts[0])),
                    )
            if retry_after > 0:
                return max(retry_after, 1)
            for key in keys:
                self._attempts[key].append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    @staticmethod
    def _prune(
        attempts: deque[float],
        *,
        now: float,
        window_seconds: int,
    ) -> None:
        while attempts and now - attempts[0] >= window_seconds:
            attempts.popleft()

    def _compact(self, *, now: float, window_seconds: int) -> None:
        stale_keys: list[str] = []
        for key, attempts in self._attempts.items():
            self._prune(attempts, now=now, window_seconds=window_seconds)
            if not attempts:
                stale_keys.append(key)
        for key in stale_keys:
            self._attempts.pop(key, None)
