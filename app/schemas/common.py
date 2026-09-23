"""Shared Pydantic types used across multiple schema modules."""

from typing import Annotated

from pydantic import StringConstraints

AssetId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$"),
]
