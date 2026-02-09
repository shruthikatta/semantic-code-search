"""Fixture module used by the chunker golden test.

Do not edit without updating tests/test_chunker.py.
"""

from __future__ import annotations

import math
from typing import Iterable

PI = 3.14159


def add(a: int, b: int = 0) -> int:
    """Return the sum of a and b."""
    return a + b


async def fetch(url: str, *, timeout: float = 1.0) -> str:
    """Fetch a URL asynchronously."""
    return url


class Calculator:
    """A toy calculator."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def add(self, x: float) -> float:
        """Add x to the running value."""
        self.value += x
        return self.value

    class Inner:
        def ping(self) -> str:
            return "pong"


def sum_iter(values: Iterable[float]) -> float:
    return math.fsum(values)
