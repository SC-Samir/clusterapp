from collections.abc import Callable
from threading import Event, Lock
from time import monotonic
from typing import TypeVar


T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._items: dict[str, tuple[float, object]] = {}
        self._inflight: dict[str, Event] = {}

    def get_or_set(self, key: str, factory: Callable[[], T]) -> T:
        while True:
            now = monotonic()
            should_compute = False

            with self._lock:
                cached = self._items.get(key)
                if cached is not None and cached[0] > now:
                    return cached[1]  # type: ignore[return-value]

                event = self._inflight.get(key)
                if event is None:
                    event = Event()
                    self._inflight[key] = event
                    should_compute = True

            if should_compute:
                try:
                    value = factory()
                except Exception:
                    with self._lock:
                        current_event = self._inflight.pop(key, None)
                        if current_event is not None:
                            current_event.set()
                    raise

                with self._lock:
                    self._items[key] = (monotonic() + self.ttl_seconds, value)
                    current_event = self._inflight.pop(key, None)
                    if current_event is not None:
                        current_event.set()
                return value

            event.wait()

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [key for key in self._items if key.startswith(prefix)]
            for key in keys:
                self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
