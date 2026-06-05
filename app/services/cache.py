from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import TypeVar


T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._items: dict[str, tuple[float, object]] = {}

    def get_or_set(self, key: str, factory: Callable[[], T]) -> T:
        now = monotonic()
        with self._lock:
            cached = self._items.get(key)
            if cached is not None and cached[0] > now:
                return cached[1]  # type: ignore[return-value]

        value = factory()

        with self._lock:
            self._items[key] = (now + self.ttl_seconds, value)
        return value

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [key for key in self._items if key.startswith(prefix)]
            for key in keys:
                self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
