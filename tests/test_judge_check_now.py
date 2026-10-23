"""Offline tests for the judge-check front door: spec parsing, probe math on fake
judges with known biases, the bundled sample, card rendering, and cost gating. No
network and no model are touched; backends are injected."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_builder.judge.backends import Backend, parse_spec, sanitize_id
from eval_builder.judge.card import Card, Meter, render_svg, write_card
from eval_builder.judge.front import build_meters, judge_check_now, verdict_block
from eval_builder.judge.sample import load_sample


class FakeJudge(Backend):
    """A backend whose answer is decided by a function of (prompt, trial)."""

    def __init__(self, fn):
        super().__init__(id="fake", kind="ollama", model="fake:model", paid=False, note="test")
        self._fn = fn

    def __call__(self, prompt: str, trial: int) -> str:  # type: ignore[override]
        return self._fn(prompt, trial)


# --- spec parsing ---------------------------------------------------------------


def test_parse_spec_ollama_keeps_colon_in_model() -> None:
    b = parse_spec("ollama:llama3.2:3b")
    assert b.kind == "ollama" and b.model == "llama3.2:3b" and not b.paid
    assert b.cost_per_call is None


def test_parse_spec_openai_is_paid_but_local_base_is_free() -> None:
    assert parse_spec("openai:gpt-4o-mini").paid is True
    local = parse_spec("openai:my-model", base_url="http://localhost:1234/v1")
    assert local.paid is False and local.cost_per_call is None


def test_parse_spec_anthropic_and_agents() -> None:
    assert parse_spec("anthropic:claude-haiku-5-5").paid is True
    assert parse_spec("claude-code").kind == "claude-code"
    assert parse_spec("codex").kind == "codex"
    assert parse_spec("claude-code").paid is False


def test_parse_spec_rejects_junk() -> None:
    with pytest.raises(ValueError):
        parse_spec("not-a-model")
    with pytest.raises(ValueError):
        parse_spec("ollama:")
    with pytest.raises(ValueError):
        parse_spec("gemini:flash")


def test_sanitize_id() -> None:
    assert sanitize_id("ollama:llama3.2:3b") == "ollama:llama3.2:3b"
    assert sanitize_id("openai:gpt-4o mini!") == "openai:gpt-4o-mini"


# --- bundled sample -------------------------------------------------------------


def test_sample_loads_and_is_balanced() -> None:
    cases, labels, meta = load_sample()
    assert meta["available"] == 80 and len(cases) == 80
    assert all(labels[c["id"]] in ("A", "B") for c in cases)
    assert all(c["compare_output"] for c in cases)  # pairwise needs a second answer


def test_sample_head_is_deterministic_and_covers_categories() -> None:
    cases, labels, meta = load_sample(16)
    assert len(cases) == 16
    assert len(load_sample(16)[0]) == 16
    assert len(meta["categories"]) >= 4  # spread across categories, not one block


# --- probe math on fake judges with known biases --------------------------------


def test_slot2_judge_scores_full_position_bias(tmp_path: Path) -> None:
    # A judge that always answers "B" follows whatever is shown in the second slot.
    r = judge_check_now(
        "ollama:fake",
        pairs=12,
        trials=3,
        probe_trials=3,
        backend=FakeJudge(lambda p, t: "B"),
        workspace=tmp_path,
        make_card=False,
    )
    assert r["coin_flip_risk"] == "HIGH" and r["verdict"] == "biased"
    pos = r["summary"]["position_probe"]
    assert pos["first_position_rate"]["rate"] == 0.0  # never the first-shown answer
    follow = next(m for m in r["metrics"] if "Follows" in m["label"])
    assert follow["value_text"] == "100%" and "second-shown" in follow["label"]
    flip = next(m for m in r["metrics"] if "Flips" in m["label"])
    assert flip["value_text"] == "0%"  # constant answer never flips


def test_coin_flip_judge_is_unstable(tmp_path: Path) -> None:
    # Independent coin per call -> flips on almost every case over several trials.
    import random

    def coin(prompt: str, trial: int) -> str:
        return random.Random(f"{hash(prompt) & 0xFFFF}-{trial}").choice(["A", "B"])

    r = judge_check_now(
        "ollama:fake",
        pairs=16,
        trials=5,
        probe_trials=3,
        backend=FakeJudge(coin),
        workspace=tmp_path,
        make_card=False,
    )
    assert r["summary"]["stability"]["flip_rate"]["rate"] > 0.6
    assert r["coin_flip_risk"] == "HIGH" and r["verdict"] == "unstable"


def test_logs_path_builds_pointwise_cases(tmp_path: Path) -> None:
    logs = tmp_path / "logs.jsonl"
    logs.write_text(
        "".join(
            json.dumps(
                {
                    "id": f"c{i}",
                    "messages": [
                        {"role": "user", "content": f"Question number {i} about topic {i % 3}?"},
                        {"role": "assistant", "content": f"Answer {i} with some detail here."},
                    ],
                }
            )
            + "\n"
            for i in range(14)
        )
    )
    r = judge_check_now(
        "ollama:fake",
        logs=[str(logs)],
        pairs=8,
        trials=3,
        probe_trials=3,
        backend=FakeJudge(lambda p, t: "pass"),
        workspace=tmp_path / "ws",
        make_card=False,
    )
    assert r["mode"] == "pointwise"
    assert r["summary"]["position_probe"] is None  # no answer order to swap
    assert r["labeled_cases"] == 0  # logs carry no human labels


# --- cost gating ----------------------------------------------------------------


def test_paid_judge_needs_yes(tmp_path: Path) -> None:
    r = judge_check_now("openai:gpt-4o-mini", pairs=6, workspace=tmp_path, make_card=False)
    assert r["needs_confirmation"] and not r["ran"]
    assert r["estimated_cost"] is not None
    assert "--yes" in verdict_block(r)


# --- card -----------------------------------------------------------------------


def test_render_svg_has_size_model_and_risk() -> None:
    card = Card(
        model="ollama:llama3.2:3b",
        risk="critical",
        headline="Follows the second-shown answer 80% of the time.",
        meters=[Meter("Flips on identical repeats", 0.5, "critical", "50%", "CI 40–60%")],
        n_text="n = 20 pairs, 220 calls",
        date="2026-10-23",
        source="MT-Bench",
        reproduce="uvx eval-builder judge-check ollama:llama3.2:3b",
    )
    svg = render_svg(card)
    assert 'width="1200" height="630"' in svg
    assert "ollama:llama3.2:3b" in svg and "HIGH" in svg
    assert "&lt;" not in card.model  # nothing to escape here, but render must not crash


def test_write_card_writes_svg(tmp_path: Path) -> None:
    card = Card("m", "good", "fine.", [], "n = 1", "2026-10-23", "src", "cmd")
    out = write_card(card, tmp_path / "card.svg")
    assert Path(out["svg"]).exists()


def test_build_meters_bands() -> None:
    j = {
        "stability": {"flip_rate": {"rate": 0.05, "ci95": [0.0, 0.2]}, "invalid_outputs": 0},
        "position_probe": {"cases": 10, "first_position_rate": {"rate": 0.5, "ci95": [0.4, 0.6]}},
        "verbosity_probe": {"cases": 10, "toward_padded": {"rate": 0.0, "ci95": [0.0, 0.1]}},
        "human_agreement": {
            "cases": 20,
            "kappa": 0.6,
            "kappa_ci95": [0.4, 0.8],
            "accuracy": {"rate": 0.8},
        },
    }
    meters, sentences = build_meters(j, "pairwise")
    assert [m.status for m in meters] == ["good", "good", "good", "good"]
    # the headline summarizes the three no-label probes; agreement stays its own meter
    assert len(sentences) == 3
