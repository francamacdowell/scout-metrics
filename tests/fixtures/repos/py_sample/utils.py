"""Utility functions for fixture testing."""

from __future__ import annotations

import re
from collections.abc import Iterable


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text


def chunk(iterable: Iterable, size: int) -> list[list]:
    """Split an iterable into chunks of given size."""
    result = []
    current: list = []
    for item in iterable:
        current.append(item)
        if len(current) == size:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result


def flatten(nested: Iterable) -> list:
    """Flatten one level of nesting."""
    out = []
    for item in nested:
        if isinstance(item, (list, tuple)):
            out.extend(item)
        else:
            out.append(item)
    return out


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
