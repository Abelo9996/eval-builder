"""Plain statistics used by judge-check. Kept small so tests can verify them by hand."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion k/n."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> tuple[float | None, float, float]:
    """Return (kappa, observed agreement po, chance agreement pe). kappa is None if pe == 1."""
    if len(a) != len(b):
        raise ValueError("rating lists must have the same length")
    n = len(a)
    if n == 0:
        return None, 0.0, 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[label] * cb[label] for label in set(ca) | set(cb)) / (n * n)
    if pe >= 1.0:
        return None, po, pe
    return (po - pe) / (1 - pe), po, pe


def kappa_interval(po: float, pe: float, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Approximate 95% interval using Cohen's (1960) large-sample standard error."""
    if n <= 0 or pe >= 1.0:
        return None
    kappa = (po - pe) / (1 - pe)
    se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    return (max(-1.0, kappa - z * se), min(1.0, kappa + z * se))


def majority(labels: Sequence[str]) -> tuple[str | None, float]:
    """Most common label and its share. Label is None when the top count is tied."""
    if not labels:
        return None, 0.0
    counts = Counter(labels).most_common()
    top, cnt = counts[0]
    if len(counts) > 1 and counts[1][1] == cnt:
        return None, cnt / len(labels)
    return top, cnt / len(labels)
