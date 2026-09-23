"""
Retry utilities for external service calls.

Provides decorators for retrying transient failures with exponential backoff.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
P = ParamSpec("P")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for first retry
        max_delay: Maximum delay in seconds between retries
        exponential_base: Base for exponential backoff calculation
        retryable_exceptions: Tuple of exception types to retry on
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                last_exception: Exception | None = None
                async_func = cast(Callable[P, Awaitable[Any]], func)
                for attempt in range(max_retries + 1):
                    try:
                        return await async_func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exception = exc
                        if attempt == max_retries:
                            logger.error(
                                "retry_exhausted",
                                function=func.__name__,
                                attempts=attempt + 1,
                                error=type(exc).__name__,
                            )
                            raise

                        # Calculate delay with jitter
                        delay = min(
                            base_delay * (exponential_base**attempt),
                            max_delay,
                        )
                        jitter = random.uniform(0, delay * 0.1)  # noqa: S311
                        total_delay = delay + jitter

                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=total_delay,
                            error=type(exc).__name__,
                        )
                        await asyncio.sleep(total_delay)

                # This should never be reached, but just in case
                if last_exception is not None:
                    raise last_exception
                raise RuntimeError("Retry loop exited without a result or exception")

            return cast(Callable[P, T], async_wrapper)
        else:

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exception: Exception | None = None
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exception = exc
                        if attempt == max_retries:
                            logger.error(
                                "retry_exhausted",
                                function=func.__name__,
                                attempts=attempt + 1,
                                error=type(exc).__name__,
                            )
                            raise

                        # Calculate delay with jitter
                        delay = min(
                            base_delay * (exponential_base**attempt),
                            max_delay,
                        )
                        jitter = random.uniform(0, delay * 0.1)  # noqa: S311
                        total_delay = delay + jitter

                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=total_delay,
                            error=type(exc).__name__,
                        )
                        time.sleep(total_delay)

                # This should never be reached, but just in case
                if last_exception is not None:
                    raise last_exception
                raise RuntimeError("Retry loop exited without a result or exception")

            return sync_wrapper

    return decorator


# Transient exceptions that are safe to retry
_TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
    ConnectionResetError,
    ConnectionRefusedError,
    ConnectionAbortedError,
)


# Common retry decorator for LLM calls — only retries transient network errors
llm_retry = retry_with_backoff(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    retryable_exceptions=_TRANSIENT_EXCEPTIONS,
)
