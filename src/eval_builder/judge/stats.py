"""Plain statistics used by judge-check. Kept small so tests can verify them by hand."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence

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


def majority_vote_stability(counts: Mapping[str, int], k: int = 3) -> float | None:
    """Chance that a majority vote over k calls (drawn without replacement from the
    observed trials) returns the same label as the majority over all trials.

    Exact hypergeometric probability that the full-majority label gets more than half
    of the k draws. None when there are fewer than k + 2 trials (too few to say
    anything beyond the full vote) or no strict majority.
    """
    n = sum(counts.values())
    if n < k + 2 or not counts:
        return None
    ordered = sorted(counts.values(), reverse=True)
    if len(ordered) > 1 and ordered[0] == ordered[1]:
        return None
    big = ordered[0]
    need = k // 2 + 1
    total = math.comb(n, k)
    hits = sum(math.comb(big, x) * math.comb(n - big, k - x) for x in range(need, k + 1))
    return hits / total
