"""
Async helper utilities.

Provides ``run_in_thread`` to offload synchronous calls to a thread pool,
preventing blocking of the asyncio event loop.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any


def run_in_thread(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: wraps a sync function to run via ``asyncio.to_thread``."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper
