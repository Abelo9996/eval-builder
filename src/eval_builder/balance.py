"""Warn when a set of cases is mostly one outcome.

On a set that is 90% "fail", a judge that always answers "fail" scores 90% accuracy.
Kappa corrects for that, but its interval gets wide, so the set itself is the problem.
"""

from __future__ import annotations

from collections.abc import Mapping

SKEW_SHARE = 0.8  # warn when one outcome is at least this share of the cases
SKEW_MIN_CASES = 5


def proportions(counts: Mapping[str, int]) -> str:
    """'fail 8 of 10 (80%), pass 2 (20%)' with the largest outcome first."""
    n = sum(counts.values())
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{items[0][0]} {items[0][1]} of {n} ({items[0][1] / n:.0%})"]
    parts += [f"{k} {v} ({v / n:.0%})" for k, v in items[1:]]
    return ", ".join(parts)


def skew_warning(
    counts: Mapping[str, int],
    what: str,
    fix: str,
    share: float = SKEW_SHARE,
    min_cases: int = SKEW_MIN_CASES,
    consequence: str | None = None,
) -> str | None:
    """A warning with the real proportions when one outcome dominates, else None.

    `consequence` replaces the default explanation; it may use {top} and {share}.
    """
    counts = {k: v for k, v in counts.items() if v}
    n = sum(counts.values())
    if n < min_cases:
        return None
    top, k = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    if k / n < share:
        return None
    if consequence:
        tail = consequence.format(top=top, share=f"{k / n:.0%}")
    elif len(counts) == 1:
        tail = (
            "there is no other outcome, so agreement on this set cannot tell a judge from "
            f"one that always answers {top!r}"
        )
    else:
        tail = (
            f"a judge that always answers {top!r} would agree on {k / n:.0%} of them, so "
            "accuracy here says little (kappa corrects for this, but read its interval)"
        )
    return f"{what} are skewed: {proportions(counts)}; {tail}. {fix}"
