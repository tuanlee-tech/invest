"""Retry utilities with exponential backoff for external API calls."""
import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Any

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Multiplier for delay after each attempt
        jitter: Add random jitter to prevent thundering herd
        exceptions: Exception types to catch and retry

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