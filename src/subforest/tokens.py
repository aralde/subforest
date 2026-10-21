"""Token estimation used for render budgets."""

from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    """Rough token count: one token per 4 characters, rounded up. Pass your own estimator for precision.

    Example:
        >>> estimate_tokens("Authentication [n31]")
        5
    """
    return math.ceil(len(text) / 4)
