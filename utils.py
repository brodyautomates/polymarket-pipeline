"""Shared utilities — retry decorator, timeouts."""
from __future__ import annotations

import functools
import logging
import random
import time

log = logging.getLogger(__name__)


def retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
    """Decorator: exponential backoff with jitter.

    Usage:
        @retry(max_attempts=3)
        def fetch_data():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.25)
                    wait = delay + jitter
                    log.warning(
                        f"[retry] {func.__name__} attempt {attempt}/{max_attempts} "
                        f"failed: {type(e).__name__}: {e} — retrying in {wait:.1f}s"
                    )
                    time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator
