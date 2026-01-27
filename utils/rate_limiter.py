"""
Simple rate limiting decorator for scraper requests.
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., object])


def rate_limit(delay_seconds: int = 2) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        last_called = {"ts": 0.0}

        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.monotonic() - last_called["ts"]
            if elapsed < delay_seconds:
                time.sleep(delay_seconds - elapsed)
            result = func(*args, **kwargs)
            last_called["ts"] = time.monotonic()
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
