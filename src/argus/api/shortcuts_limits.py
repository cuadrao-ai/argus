"""Weighted sliding-window counter for Shortcuts intake budgets.

``SlidingWindowLimiter`` counts one hit per call and has no read-only check.
Intake also needs to spend several events at once (a pending batch) and to
ask "is this address already blocked?" before authenticating, so this small
counter adds both. Like every limiter here it is process-local: each API
process keeps its own counts and a restart forgets them.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class WeightedWindow:
    def __init__(self, *, compact_threshold: int = 4096) -> None:
        self._hits: defaultdict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._lock = Lock()
        self._compact_threshold = compact_threshold

    def spend(self, key: str, weight: int, *, limit: int, window: int) -> int | None:
        """Record ``weight`` unless it would exceed ``limit``; else seconds to wait."""

        now = monotonic()
        with self._lock:
            hits = self._current(key, now, window)
            used = sum(w for _, w in hits)
            if used + weight > limit:
                return self._wait(hits, now, window)
            hits.append((now, weight))
            return None

    def blocked(self, key: str, *, limit: int, window: int) -> int | None:
        """Seconds to wait when ``limit`` is already reached; never records."""

        now = monotonic()
        with self._lock:
            hits = self._current(key, now, window)
            if sum(w for _, w in hits) < limit:
                return None
            return self._wait(hits, now, window)

    def refund(self, key: str, weight: int, *, window: int) -> None:
        """Give back the newest ``weight`` spent on ``key`` (a released reservation)."""

        now = monotonic()
        with self._lock:
            hits = self._current(key, now, window)
            for index in range(len(hits) - 1, -1, -1):
                if hits[index][1] == weight:
                    del hits[index]
                    return

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _current(self, key: str, now: float, window: int) -> deque[tuple[float, int]]:
        if len(self._hits) >= self._compact_threshold:
            # One window per instance, so compaction never drops live history.
            for stale in [k for k, v in self._hits.items() if _prune(v, now, window)]:
                self._hits.pop(stale, None)
        hits = self._hits[key]
        _prune(hits, now, window)
        return hits

    @staticmethod
    def _wait(hits: deque[tuple[float, int]], now: float, window: int) -> int:
        oldest = hits[0][0] if hits else now
        return max(int(window - (now - oldest)), 1)


def _prune(hits: deque[tuple[float, int]], now: float, window: int) -> bool:
    while hits and now - hits[0][0] >= window:
        hits.popleft()
    return not hits
