"""HTML-escape helpers for preventing prompt injection (SEC-2)."""

import html
from typing import Any


def escape_value(v: Any) -> Any:
    """Recursively escape a value to prevent prompt injection.

    Strings are HTML-escaped; dicts and lists are processed recursively;
    all other values are returned unchanged.
    """
    if isinstance(v, str):
        return html.escape(v)
    elif isinstance(v, dict):
        return escape_dict(v)
    elif isinstance(v, list):
        return [escape_value(item) for item in v]
    return v


def escape_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively HTML-escape string values in a dictionary."""
    result = {}
    for k, v in d.items():
        result[k] = escape_value(v)
    return result
