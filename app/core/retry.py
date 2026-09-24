"""Retry utilities with exponential backoff for external API calls."""
import time
import logging
from functools import wraps
from typing import Callable, Optional, Type, Tuple, Any

logger = logging.getLogger(__name__)

# Markers of transient network/provider failures (matched against str(exc).lower())
_TRANSIENT_MARKERS = (
    "timeout", "timed out", "temporarily", "connection aborted",
    "connection refused", "connection reset", "connection unreachable",
    "max retries", "remote end closed", "broken pipe", "read timed out",
    "rate limit", "too many requests", "service unavailable",
    " 502", " 503", " 504", "http 502", "http 503", "http 504",
    "http 429", "status 502", "status 503", "status 504", "status 429",
)


def is_transient_error(exc: BaseException) -> bool:
    """True only for failures worth retrying (timeout/connection/5xx/429).

    Permanent errors (invalid symbol, bad response shape, ValueError, …)
    return False so the caller fails fast instead of hammering the provider.
    """
    import requests

    if isinstance(exc, requests.exceptions.HTTPError):
        code = getattr(exc.response, "status_code", None)
        return code in (408, 425, 429, 500, 502, 503, 504)
    if isinstance(exc, requests.exceptions.RequestException):
        # InvalidURL/InvalidSchema/MissingSchema are permanent config errors
        return not isinstance(
            exc,
            (requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema,
             requests.exceptions.MissingSchema),
        )
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, OSError):
        return True  # socket-level hiccups
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    retry_if: Optional[Callable[[Exception], bool]] = None,
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        base_delay: Initial delay in seconds
        max_delay: Delay cap in seconds
        exponential_base: Multiplier for delay after each attempt
        jitter: Add random jitter to prevent thundering herd
        exceptions: Exception types to catch and retry
        retry_if: Optional predicate — return False to fail fast (no retry)

    Usage:
        @retry(max_attempts=3, base_delay=1.0, exceptions=(requests.RequestException,))
        def fetch_data():
            return requests.get(url).json()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if retry_if is not None and not retry_if(e):
                        logger.error(
                            f"{func.__name__} failed with a non-retryable error: {e}"
                        )
                        raise

                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)

                    # Add jitter
                    if jitter:
                        import random
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # Should not reach here, but just in case
            raise last_exception

        return wrapper
    return decorator


# Specific retry decorators for common use cases
vnstock_retry = retry(
    max_attempts=3,
    base_delay=2.0,
    max_delay=30.0,
    exceptions=(Exception,),  # vnstock raises generic exceptions
    retry_if=is_transient_error,  # permanent errors (bad symbol, malformed) fail fast
)

llm_retry = retry(
    max_attempts=2,
    base_delay=5.0,
    max_delay=60.0,
    exceptions=(Exception,),  # OpenCode CLI failures
)

network_retry = retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    exceptions=(ConnectionError, TimeoutError, IOError),
)