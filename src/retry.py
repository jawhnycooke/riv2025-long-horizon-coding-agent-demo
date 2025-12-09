"""Retry logic for transient API and network failures.

Provides exponential backoff with jitter for reliable API calls.
Distinguishes between transient errors (retry) and permanent errors (fail fast).

Key features:
- Exponential backoff with configurable base and max delay
- Jitter to prevent thundering herd
- Configurable max retries
- HTTP status code classification (transient vs permanent)
- Async support for async functions
- Logging of retry attempts
"""

import asyncio
import functools
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar


logger = logging.getLogger(__name__)

# Type variables for generic decorator
T = TypeVar("T")
P = ParamSpec("P")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        jitter: Whether to add random jitter to delays (default: True)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


# HTTP status codes that indicate transient errors (should retry)
TRANSIENT_STATUS_CODES: frozenset[int] = frozenset(
    {
        429,  # Rate limited
        500,  # Internal server error
        502,  # Bad gateway
        503,  # Service unavailable
        504,  # Gateway timeout
    }
)

# HTTP status codes that indicate permanent errors (should not retry)
PERMANENT_STATUS_CODES: frozenset[int] = frozenset(
    {
        400,  # Bad request
        401,  # Unauthorized
        403,  # Forbidden
        404,  # Not found
        405,  # Method not allowed
        409,  # Conflict
        422,  # Unprocessable entity
    }
)


class RetryableError(Exception):
    """Exception that indicates a retryable error.

    Use this to wrap errors that should trigger retry logic.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize retryable error.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
            original_error: Original exception that was caught
        """
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


class PermanentError(Exception):
    """Exception that indicates a permanent error (should not retry).

    Use this to wrap errors that should fail immediately.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize permanent error.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
            original_error: Original exception that was caught
        """
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and should be retried.

    Args:
        error: The exception to check

    Returns:
        True if the error is transient and should be retried
    """
    # RetryableError is always transient
    if isinstance(error, RetryableError):
        return True

    # PermanentError is never transient
    if isinstance(error, PermanentError):
        return False

    # Check for status_code attribute (common in HTTP libraries)
    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        if status_code in TRANSIENT_STATUS_CODES:
            return True
        if status_code in PERMANENT_STATUS_CODES:
            return False

    # Check for response attribute (requests library pattern)
    response = getattr(error, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status is not None:
            if status in TRANSIENT_STATUS_CODES:
                return True
            if status in PERMANENT_STATUS_CODES:
                return False

    # Common network error types (transient)
    transient_error_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    if isinstance(error, transient_error_types):
        return True

    # Check error message for common transient patterns
    error_str = str(error).lower()
    transient_patterns = [
        "timeout",
        "connection refused",
        "connection reset",
        "temporarily unavailable",
        "rate limit",
        "throttl",
        "overloaded",
        "too many requests",
    ]
    # Return True if transient pattern found, otherwise False (fail fast)
    return any(pattern in error_str for pattern in transient_patterns)


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate the delay before the next retry attempt.

    Uses exponential backoff with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = config.base_delay * (config.exponential_base**attempt)

    # Cap at max_delay
    delay = min(delay, config.max_delay)

    # Add jitter (random value between 0 and delay)
    if config.jitter:
        delay = delay * (0.5 + random.random())

    return delay


def with_retry(
    config: RetryConfig | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for retrying synchronous functions on transient failures.

    Args:
        config: Retry configuration (uses defaults if None)

    Returns:
        Decorated function that retries on transient errors

    Example:
        @with_retry(RetryConfig(max_retries=5))
        def call_api():
            response = requests.get("https://api.example.com")
            response.raise_for_status()
            return response.json()
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not is_transient_error(e):
                        logger.warning(
                            "Permanent error in %s: %s (not retrying)",
                            func.__name__,
                            e,
                        )
                        raise

                    if attempt >= config.max_retries:
                        logger.error(
                            "Max retries (%d) exceeded for %s: %s",
                            config.max_retries,
                            func.__name__,
                            e,
                        )
                        raise

                    delay = calculate_delay(attempt, config)
                    logger.info(
                        "Transient error in %s (attempt %d/%d): %s. "
                        "Retrying in %.2fs",
                        func.__name__,
                        attempt + 1,
                        config.max_retries + 1,
                        e,
                        delay,
                    )
                    time.sleep(delay)

            # Should not reach here, but satisfy type checker
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


def with_async_retry(
    config: RetryConfig | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for retrying async functions on transient failures.

    Args:
        config: Retry configuration (uses defaults if None)

    Returns:
        Decorated async function that retries on transient errors

    Example:
        @with_async_retry(RetryConfig(max_retries=5))
        async def call_api():
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.example.com") as response:
                    response.raise_for_status()
                    return await response.json()
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            last_error: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not is_transient_error(e):
                        logger.warning(
                            "Permanent error in %s: %s (not retrying)",
                            func.__name__,
                            e,
                        )
                        raise

                    if attempt >= config.max_retries:
                        logger.error(
                            "Max retries (%d) exceeded for %s: %s",
                            config.max_retries,
                            func.__name__,
                            e,
                        )
                        raise

                    delay = calculate_delay(attempt, config)
                    logger.info(
                        "Transient error in %s (attempt %d/%d): %s. "
                        "Retrying in %.2fs",
                        func.__name__,
                        attempt + 1,
                        config.max_retries + 1,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)

            # Should not reach here, but satisfy type checker
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


# Default retry configuration (can be overridden via config file)
_default_config: RetryConfig = RetryConfig()


def get_default_retry_config() -> RetryConfig:
    """Get the default retry configuration.

    Returns:
        Default RetryConfig instance
    """
    return _default_config


def set_default_retry_config(config: RetryConfig) -> None:
    """Set the default retry configuration.

    Args:
        config: New default configuration
    """
    global _default_config
    _default_config = config


def init_retry_config(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
) -> RetryConfig:
    """Initialize retry configuration from parameters.

    Args:
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Configured RetryConfig instance
    """
    config = RetryConfig(
        max_retries=max_retries if max_retries is not None else 3,
        base_delay=base_delay if base_delay is not None else 1.0,
        max_delay=max_delay if max_delay is not None else 60.0,
    )
    set_default_retry_config(config)
    return config
