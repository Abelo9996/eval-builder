"""The bundled, human-labeled sample used when the user passes no logs of their own.

80 MT-Bench turn-1 pairwise comparisons with an expert human winner (CC BY 4.0). See
data/sample/CREDITS.md. Shaped into eval-builder cases so the probes and the human
agreement check run with zero setup.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

CITATION = (
    "LMSYS MT-Bench human judgments (CC BY 4.0), Zheng et al. 2023, "
    "'Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena'"
)


def _rows() -> list[dict[str, Any]]:
    text = (files("eval_builder.data.sample") / "mt_bench_pairs.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_sample(
    n: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Return (cases, human_labels, meta). Cases are shaped for build_requests."""
    rows = _rows()
    if n is not None:
        rows = _balanced_head(rows, n)
    cases: list[dict[str, Any]] = []
    labels: dict[str, str] = {}
    for r in rows:
        cases.append(
            {
                "id": r["id"],
                "trace_id": r["id"],
                "status": "ready",
                "input": r["input"],
                "observed_output": r["answer_a"],
                "compare_output": r["answer_b"],
                "expected_behavior": "The more helpful, relevant, accurate and detailed "
                "answer to the user's question is better.",
                "criteria": ["overall-quality"],
                "tags": [f"category:{r['category']}"],
            }
        )
        labels[r["id"]] = r["human_label"]
    meta = {
        "source": "mt_bench_pairs",
        "citation": CITATION,
        "available": len(_rows()),
        "used": len(cases),
        "categories": sorted({r["category"] for r in rows}),
    }
    return cases, labels, meta


def _balanced_head(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Take n rows spread evenly across categories and keeping A/B labels close to even.

    Deterministic: walks the categories round-robin in their fixed order, and within a
    category alternates the two human-winner labels so a short run stays balanced.
    """
    if n >= len(rows):
        return rows
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda r: (r["human_label"], r["id"]))
    order = list(by_cat)
    picked: list[dict[str, Any]] = []
    idx = dict.fromkeys(order, 0)
    while len(picked) < n and any(idx[c] < len(by_cat[c]) for c in order):
        for c in order:
            if idx[c] < len(by_cat[c]) and len(picked) < n:
                picked.append(by_cat[c][idx[c]])
                idx[c] += 1
    return picked
