import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import TypeVar

T = TypeVar("T")


class TTLCache:
    """Async-only TTL cache with single-flight deduplication.

    - One asyncio.Lock guards _items, _inflight, and _inflight_waiters so
      invalidation and population never race (the previous implementation used
      separate threading/asyncio locks and could drop invalidations).
    - Lazy expiry: expired entries are treated as misses and overwritten.
    - Single-flight: concurrent callers for the same key share one computation;
      waiters register under the lock so a late arrival after the producer
      finishes still gets the freshly cached value instead of recomputing.
    """

    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._items: dict[str, tuple[float, object]] = {}
        self._inflight: dict[str, asyncio.Future[object]] = {}

    async def get_or_set_async(
        self, key: str, factory: Callable[[], "Awaitable[T] | T"]
    ) -> T:
        while True:
            now = monotonic()
            async with self._lock:
                cached = self._items.get(key)
                if cached is not None and cached[0] > now:
                    return cached[1]  # type: ignore[return-value]

                future = self._inflight.get(key)
                if future is None:
                    future = asyncio.get_running_loop().create_future()
                    self._inflight[key] = future
                    should_compute = True
                else:
                    should_compute = False

            if should_compute:
                try:
                    value = factory()
                    if asyncio.iscoroutine(value):
                        value = await value
                except Exception as exc:
                    async with self._lock:
                        self._inflight.pop(key, None)
                        future.set_exception(exc)
                    raise

                async with self._lock:
                    self._items[key] = (monotonic() + self.ttl_seconds, value)
                    self._inflight.pop(key, None)
                    future.set_result(value)
                return value  # type: ignore[return-value]

            # Wait for the in-flight producer. If it already finished by the
            # time we await, loop back and read the cached value (avoids
            # propagating a cancelled/exceptional future to unrelated waiters).
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Producer failed; loop back. If we're the next waiter we'll
                # become the new producer; otherwise we'll wait on a new future.
                continue

    async def invalidate_prefix(self, prefix: str) -> None:
        async with self._lock:
            for key in [k for k in self._items if k.startswith(prefix)]:
                self._items.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()