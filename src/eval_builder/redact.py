"""Default-on redaction of obvious secrets and PII.

Patterns are deliberately conservative: they catch common key formats, emails,
card numbers that pass a Luhn check, US-style phone numbers with separators, and
SSN-shaped numbers. They are not a DLP system; the report lists exactly what was
replaced so you can check.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"(?<![\d-])(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\d-])")),
    ("credit_card", re.compile(r"\b\d(?:[ -]?\d){12,18}\b")),
]


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class Redactor:
    """Replaces matches with [REDACTED_<KIND>] and counts what it replaced."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.counts: Counter[str] = Counter()
        self.by_trace: dict[str, Counter[str]] = {}
        self._current: str | None = None

    def start_trace(self, trace_id: str) -> None:
        self._current = trace_id

    def text(self, s: str, count: bool = True) -> str:
        """Redact one string. count=False redacts text already counted elsewhere."""
        if not self.enabled or not s:
            return s
        for kind, pat in _PATTERNS:

            def repl(m: re.Match[str], kind: str = kind) -> str:
                return self._replace(kind, m.group(0), count)

            s = pat.sub(repl, s)
        return s

    def _replace(self, kind: str, match: str, count: bool = True) -> str:
        if kind == "credit_card":
            digits = re.sub(r"\D", "", match)
            if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                return match
        if not count:
            return f"[REDACTED_{kind.upper()}]"
        self.counts[kind] += 1
        if self._current is not None:
            self.by_trace.setdefault(self._current, Counter())[kind] += 1
        return f"[REDACTED_{kind.upper()}]"

    def value(self, v: Any) -> Any:
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if isinstance(v, dict):
            return {k: self.value(x) for k, x in v.items()}
        return v

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "total": sum(self.counts.values()),
            "by_kind": dict(sorted(self.counts.items())),
            "traces_affected": len(self.by_trace),
            "by_trace": {t: dict(c) for t, c in sorted(self.by_trace.items())},
            "note": "Values are replaced with [REDACTED_<KIND>]; originals are never written.",
        }
