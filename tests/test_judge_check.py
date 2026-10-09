from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_builder.judge.check import (
    Thresholds,
    check_judge,
    judge_check,
    normalize_verdict,
)


def rows(
    judge: str,
    case: str,
    verdicts: list[str],
    probe: str = "none",
    pad_side: str | None = None,
    mode: str = "pairwise",
) -> list[dict]:
    return [
        {
            "judge": judge,
            "case_id": case,
            "mode": mode,
            "probe": probe,
            "trial": t,
            "pad_side": pad_side,
            "verdict": v,
        }
        for t, v in enumerate(verdicts)
    ]


TH = Thresholds(
    min_trials=3,
    min_cases=4,
    min_labeled=4,
    max_flip_rate=0.2,
    min_position_consistency=0.8,
    max_toward_padded_rate=0.1,
    min_kappa=0.4,
)


def test_normalize_verdict() -> None:
    assert normalize_verdict("A", "pairwise") == "A"
    assert normalize_verdict("**B**", "pairwise") == "B"
    assert normalize_verdict("[[A]]", "pairwise") == "A"
    assert normalize_verdict("Assistant B is better", "pairwise") == "B"
    assert normalize_verdict("[[C]]", "pairwise") == "tie"
    assert normalize_verdict("I think both", "pairwise") == "invalid"
    assert normalize_verdict(None, "pairwise") == "invalid"
    assert normalize_verdict("PASS.", "pointwise") == "pass"
    assert normalize_verdict(4.0, "pointwise") == "4"
    assert normalize_verdict(True, "pointwise") == "pass"
    # JSON answers, for example a judge written for promptfoo's llm-rubric
    assert normalize_verdict('{"pass": false, "reason": "no code"}', "pointwise") == "fail"
    assert normalize_verdict({"pass": True}, "pointwise") == "pass"
    assert normalize_verdict('{"verdict": "B"}', "pairwise") == "B"
    assert normalize_verdict('{"reason": "unsure"}', "pointwise") == "invalid"


def test_flip_rate_kappa_and_trustworthy() -> None:
    # 5 cases, 3 trials each; case c4 has one flip -> flip rate 1/5 = 0.2 (not > 0.2)
    data = (
        rows("j", "c0", ["A", "A", "A"])
        + rows("j", "c1", ["B", "B", "B"])
        + rows("j", "c2", ["A", "A", "A"])
        + rows("j", "c3", ["B", "B", "B"])
        + rows("j", "c4", ["A", "A", "B"])
    )
    labels = {"c0": "A", "c1": "B", "c2": "A", "c3": "B", "c4": "B"}
    r = check_judge(data, labels, TH)
    st = r["stability"]
    assert st["flip_rate"]["k"] == 1 and st["flip_rate"]["rate"] == 0.2
    # self-agreement = (1 + 1 + 1 + 1 + 2/3) / 5
    assert st["mean_self_agreement"] == pytest.approx(0.9333, abs=1e-4)
    ag = r["human_agreement"]
    # majorities A,B,A,B,A vs labels A,B,A,B,B: 4/5 correct
    # po = 0.8; judge A=3/5, B=2/5; human A=2/5, B=3/5; pe = 0.24 + 0.24 = 0.48
    # kappa = (0.8 - 0.48) / 0.52 = 0.6154
    assert ag["accuracy"]["k"] == 4 and ag["kappa"] == pytest.approx(0.6154, abs=1e-4)
    assert ag["chance_agreement"] == pytest.approx(0.48)
    # single calls: 12 of 12 on c0-c3, 1 of 3 on c4 -> 13/15
    assert ag["single_call_accuracy"] == pytest.approx(13 / 15, abs=1e-4)
    assert r["verdict"] == "trustworthy"
    assert r["checks"]["position"] == "not run"


def test_unstable() -> None:
    data = []
    for i in range(5):
        data += rows("j", f"c{i}", ["A", "B", "A"] if i < 2 else ["A", "A", "A"])
    r = check_judge(data, {}, TH)
    assert r["stability"]["flip_rate"]["rate"] == 0.4
    assert r["verdict"] == "unstable"


def test_position_bias_detected_and_unswapped() -> None:
    # The judge always says "A" whatever is shown first.
    data = []
    labels = {}
    for i in range(5):
        data += rows("j", f"c{i}", ["A", "A", "A"])
        data += rows("j", f"c{i}", ["A", "A", "A"], probe="swap")
        labels[f"c{i}"] = "A"
    r = check_judge(data, labels, TH)
    pos = r["position_probe"]
    # swapped "A" means original "B": the majority never survives the swap
    assert pos["consistency"]["k"] == 0 and pos["consistency"]["n"] == 5
    assert pos["first_position_rate"]["rate"] == 1.0
    assert r["verdict"] == "biased"


def test_verbosity_bias_pairwise() -> None:
    data = []
    labels = {}
    for i in range(5):
        side = "A" if i % 2 == 0 else "B"
        other = "B" if side == "A" else "A"
        data += rows("j", f"c{i}", [other] * 3)
        # padding flips 2 of the 5 cases toward the padded answer
        data += rows("j", f"c{i}", [side if i < 2 else other] * 3, probe="pad", pad_side=side)
        labels[f"c{i}"] = other
    r = check_judge(data, labels, TH)
    v = r["verbosity_probe"]
    assert v["changed"]["k"] == 2 and v["toward_padded"]["k"] == 2
    assert v["toward_padded"]["rate"] == 0.4
    assert r["verdict"] == "biased"


def test_verbosity_pointwise_numeric_scores() -> None:
    data = []
    for i in range(4):
        data += rows("j", f"c{i}", ["3", "3", "3"], mode="pointwise")
        data += rows(
            "j",
            f"c{i}",
            ["4", "4", "4"] if i == 0 else ["3"] * 3,
            probe="pad",
            pad_side="output",
            mode="pointwise",
        )
    r = check_judge(data, {}, TH)
    assert r["verbosity_probe"]["toward_padded"]["k"] == 1


def test_misaligned_and_not_enough_data() -> None:
    data = []
    labels = {}
    for i in range(5):
        data += rows("j", f"c{i}", ["A"] * 3)
        labels[f"c{i}"] = "B" if i < 3 else "A"
    r = check_judge(data, labels, TH)
    # constant judge: kappa 0
    assert r["human_agreement"]["kappa"] == pytest.approx(0.0)
    assert r["verdict"] == "misaligned"
    r = check_judge(data, {}, TH)
    assert r["verdict"] == "not_enough_data" and "human labels" in r["reasons"][-1]
    r = check_judge(rows("j", "c0", ["A"] * 3), {}, TH)
    assert r["verdict"] == "not_enough_data" and "only 1 case" in r["reasons"][0]
    r = check_judge(rows("j", "c0", ["A"]) + rows("j", "c1", ["B"]), {}, TH)
    assert r["stability"]["cases"] == 0  # single trials never count toward stability


def test_judge_check_files_and_request_join(tmp_path: Path) -> None:
    ws = tmp_path
    req = [
        {
            "request_id": f"j:c{i}:none:{t}",
            "judge": "j",
            "case_id": f"c{i}",
            "mode": "pairwise",
            "probe": "none",
            "trial": t,
            "pad_side": None,
            "presented": {},
            "prompt": "p",
        }
        for i in range(4)
        for t in range(3)
    ]
    (ws / "judge_requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in req))
    # judgments may carry only request_id + verdict
    (ws / "judgments.jsonl").write_text(
        "".join(json.dumps({"request_id": r["request_id"], "verdict": "A"}) + "\n" for r in req)
    )
    (ws / "labels.jsonl").write_text(
        "".join(json.dumps({"case_id": f"c{i}", "label": "model_a"}) + "\n" for i in range(4))
        + json.dumps({"case_id": "c0", "label": "B"})
        + "\n"
        + json.dumps({"case_id": "c0", "label": "A"})
        + "\n"
    )
    r = judge_check(ws, thresholds=TH)
    assert r["labeled_cases"] == 4
    j = r["judges"]["j"]
    assert j["human_agreement"]["accuracy"]["k"] == 4
    assert j["human_agreement"]["kappa"] is None  # everyone says A: chance agreement is 1
    assert (ws / "judge_check.json").exists()
    # the summary carries the intervals and sample sizes, so MCP callers need no file reads
    s = r["summary"][0]
    assert s["cases"] == 4 and s["labeled_cases"] == 4 and s["flip_rate_ci95"] is not None
    assert s["accuracy_ci95"] == j["human_agreement"]["accuracy"]["ci95"]
    assert r["next"].startswith("no judge passed")  # 4 labels meet this test's min_labeled


def test_judge_check_missing_judgments_says_how(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run judge_plan first"):
        judge_check(tmp_path)


def test_judge_no_better_than_majority_label_is_not_trustworthy():
    from eval_builder.judge.check import Thresholds, _verdict

    stability = {"cases": 24, "flip_rate": {"rate": 0.0}}
    # kappa clears 0.4, but 75% accuracy only matches always answering "fail" (18 of 24)
    agreement = {
        "cases": 24,
        "kappa": 0.5,
        "accuracy": {"rate": 0.75},
        "majority_baseline": 0.75,
        "human_label_counts": {"fail": 18, "pass": 6},
    }
    verdict, reasons, checks = _verdict(stability, agreement, None, None, Thresholds())
    assert verdict == "misaligned"
    assert checks["human_agreement"] == "fail"
    assert "no better than always answering 'fail'" in reasons[-1]

    better = dict(agreement, accuracy={"rate": 0.875})
    assert _verdict(stability, better, None, None, Thresholds())[0] == "trustworthy"
    off = Thresholds(beat_majority_baseline=False)
    assert _verdict(stability, agreement, None, None, off)[0] == "trustworthy"
