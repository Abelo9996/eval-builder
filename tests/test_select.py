from __future__ import annotations

from eval_builder.schema import Trace
from eval_builder.select import near_duplicate_groups, select_traces, text_hash


def T(i: int, inp: str, out: str = "ok", **kw) -> Trace:
    return Trace(
        id=f"t{i}",
        input=inp,
        output=out,
        messages=[{"role": "user", "content": inp}, {"role": "assistant", "content": out}],
        **kw,
    )


def test_text_hash_normalizes_case_and_whitespace() -> None:
    assert text_hash("Hello   World\n") == text_hash("hello world")
    assert text_hash("hello world") != text_hash("hello there")


def test_near_duplicate_groups() -> None:
    texts = [
        "How do I reset my password on the mobile app?",
        "How do I reset my password on the mobile app ?!",
        "What is the capital of France?",
    ]
    assert near_duplicate_groups(texts, 0.9) == [[0, 1], [2]]
    assert near_duplicate_groups(texts, 0.999) == [[0], [1], [2]]


def test_exact_dedupe_prefers_failing_representative() -> None:
    traces = [
        T(0, "Reset password"),
        T(1, "reset   PASSWORD", feedback="negative"),
        T(2, "Weather in Paris"),
    ]
    r = select_traces(traces, n=5)
    assert r["population"]["exact_duplicates_removed"] == 1
    picked = {s["trace_id"]: s for s in r["selected"]}
    assert "t1" in picked and "t0" not in picked
    assert picked["t1"]["represents"] == 2 and picked["t1"]["duplicates"] == ["t0"]
    assert picked["t1"]["failing_in_group"] == 1


def test_same_followup_different_conversation_not_merged() -> None:
    def conv(i: int, first: str) -> Trace:
        msgs = [
            {"role": "user", "content": first},
            {"role": "assistant", "content": "x"},
            {"role": "user", "content": "Make it shorter."},
            {"role": "assistant", "content": "y"},
        ]
        return Trace(id=f"c{i}", input="Make it shorter.", output="y", messages=msgs)

    r = select_traces([conv(0, "Write a poem about rain"), conv(1, "Summarize this contract")], n=5)
    assert r["population"]["unique"] == 2


def _population() -> list[Trace]:
    topics = {
        "billing": [
            "Why was I charged twice this month",
            "Refund my last invoice please",
            "Update the credit card on my billing account",
            "Invoice shows wrong tax",
            "Cancel my subscription billing",
            "Billing date change request",
        ],
        "shipping": [
            "Where is my package tracking number",
            "Package arrived damaged box",
            "Change shipping address for order",
            "Shipping is late by a week",
            "International shipping cost to Canada",
            "Express shipping options",
        ],
        "account": [
            "Reset my account password",
            "Enable two factor login on account",
            "Delete my account and data",
            "Change account email address",
            "Account locked after login attempts",
            "Merge two accounts together",
        ],
    }
    traces = []
    i = 0
    for route, inputs in topics.items():
        for inp in inputs:
            traces.append(
                T(
                    i,
                    inp,
                    route=route,
                    tools=["kb_search"] if i % 5 == 0 else [],
                    error=(i % 7 == 3),
                )
            )
            i += 1
    traces[4].feedback = "negative"
    traces.append(T(i, "Do you sell gift cards", route="sales"))  # rare route
    return traces


def test_selection_covers_failures_strata_and_clusters() -> None:
    traces = _population()
    r = select_traces(traces, n=8, seed=0, clusters=3, failure_share=0.3)
    assert r["selected_count"] == 8
    sel = {s["trace_id"]: s for s in r["selected"]}
    failures = {t.id for t in traces if t.error or t.feedback == "negative"}
    # ceil(0.3 * 8) = 3 failures reserved; population has 4
    assert len(failures & set(sel)) >= 3
    # the rare route and the tool stratum are covered, with a reason that says so
    assert "t18" in sel and any("route=sales" in x for x in sel["t18"]["reasons"])
    assert r["strata"]["tools"]["kb_search"]["selected"] >= 1
    # every cluster has at least one pick
    assert all(c["selected"] >= 1 for c in r["clusters"])
    # every pick has at least one reason
    assert all(s["reasons"] for s in r["selected"])
    assert r["strata"]["route"]["sales"] == {"population": 1, "selected": 1}


def test_selection_is_deterministic() -> None:
    a = select_traces(_population(), n=7, seed=3)
    b = select_traces(_population(), n=7, seed=3)
    assert [s["trace_id"] for s in a["selected"]] == [s["trace_id"] for s in b["selected"]]


def test_budget_larger_than_population_selects_all() -> None:
    traces = _population()
    r = select_traces(traces, n=100)
    assert r["selected_count"] == len(traces)


def test_high_cardinality_metadata_not_stratified() -> None:
    words = [
        "elephants",
        "volcanoes",
        "jazz",
        "taxes",
        "bridges",
        "tulips",
        "comets",
        "sushi",
        "chess",
        "glaciers",
        "pianos",
        "deserts",
        "robots",
        "coral",
        "vaccines",
        "castles",
        "kayaks",
        "lasers",
        "owls",
        "quilts",
        "rockets",
        "saffron",
        "tides",
        "yoga",
        "zebras",
        "canyons",
        "ferns",
        "geysers",
        "mosaics",
        "nebulae",
    ]
    traces = [T(i, f"Tell me about {w}", metadata={"user": f"u{i}"}) for i, w in enumerate(words)]
    r = select_traces(traces, n=6, stratify=["user"])
    assert "user" in r["strata_skipped"]
