"""Retry decorator with exponential backoff for Ictus Flow API calls.

Retries on transient failures (network errors, rate limits, server errors)
and raises immediately on permanent errors (bad request, not found, auth).

Usage:
    from scripts.utils.retry import retry_with_backoff

    @retry_with_backoff(max_retries=3, base_delay=2)
    def call_api():
        ...

Delays: base_delay * 2^attempt + jitter (0-1s)
  attempt 0: 2s + jitter
  attempt 1: 4s + jitter
  attempt 2: 8s + jitter
"""

import time
import random
import functools

# HTTP status codes that are safe to retry
RETRYABLE_HTTP_CODES = {429, 500, 502, 503}


def _is_retryable(exc):
    """Determine whether an exception is transient and worth retrying.

    Uses lazy imports so the decorator works even if a library isn't installed.
    """
    # Python builtins — network-level failures
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    # Google API client — HttpError with retryable status
    try:
        from googleapiclient.errors import HttpError
        if isinstance(exc, HttpError):
            return exc.resp.status in RETRYABLE_HTTP_CODES
    except ImportError:
        pass

    # Anthropic — connection / rate-limit / server errors
    try:
        from anthropic import APIConnectionError, RateLimitError, InternalServerError
        if isinstance(exc, (APIConnectionError, RateLimitError, InternalServerError)):
            return True
    except ImportError:
        pass

    # Resend — rate limit / application errors (server-side)
    try:
        from resend.exceptions import RateLimitError as ResendRateLimitError
        from resend.exceptions import ApplicationError as ResendAppError
        if isinstance(exc, (ResendRateLimitError, ResendAppError)):
            return True
    except ImportError:
        pass

    # Requests (used by resend under the hood)
    try:
        from requests.exceptions import ConnectionError as ReqConnectionError
        from requests.exceptions import Timeout as ReqTimeout
        if isinstance(exc, (ReqConnectionError, ReqTimeout)):
            return True
    except ImportError:
        pass

    return False


def retry_with_backoff(max_retries=3, base_delay=2):
    """Decorator that retries a function on transient failures.

    Args:
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Base delay in seconds before first retry (default 2).
                    Doubles each attempt: 2s, 4s, 8s.
                    Random jitter (0-1s) is added to prevent thundering herd.

    Raises:
        The original exception after all retries are exhausted,
        or immediately if the error is not retryable.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not _is_retryable(exc):
                        raise

                    if attempt == max_retries:
                        raise

                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(
                        f"[RETRY] {func.__name__} attempt {attempt + 1}/{max_retries} "
                        f"failed: {exc}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
