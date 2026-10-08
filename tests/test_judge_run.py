from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from eval_builder.judge.plan import PAD_TEXT, build_requests, judge_plan
from eval_builder.judge.run import PluginDisabled, judge_run

ECHO_JUDGE = """
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    print(json.dumps({"verdict": "pass" if req["trial"] % 2 == 0 else "fail",
                      "raw": req["prompt"][:5], "tokens": 3}), flush=True)
"""


def test_plan_pointwise_with_pad(ready_workspace: Path) -> None:
    r = judge_plan(ready_workspace, trials=3, probes=["pad", "swap"], probe_trials=2)
    rows = [json.loads(x) for x in (ready_workspace / "judge_requests.jsonl").open()]
    # 5 cases x (3 trials + 2 pad); swap is skipped for pointwise judges
    assert r["requests"] == len(rows) == 25
    pad = [x for x in rows if x["probe"] == "pad"]
    assert all(x["presented"]["output"].endswith(PAD_TEXT) for x in pad)
    assert all(x["prompt"].startswith("Q: ") and "{input}" not in x["prompt"] for x in rows)
    assert {x["probe"] for x in rows} == {"none", "pad"}


def test_plan_renders_context_placeholder() -> None:
    cases = [
        {
            "id": "c0",
            "input": "shorter please",
            "observed_output": "ok",
            "context": [
                {"role": "user", "content": "write a poem"},
                {"role": "assistant", "content": "roses..."},
            ],
        },
        {"id": "c1", "input": "hi", "observed_output": "hello"},
    ]
    rubric = {
        "criteria": [],
        "judges": [{"id": "j", "labels": ["pass", "fail"], "prompt": "{context}|{input}|{output}"}],
    }
    rows = build_requests(cases, rubric, trials=1)
    assert rows[0]["prompt"] == "user: write a poem\n\nassistant: roses...|shorter please|ok"
    assert rows[1]["prompt"] == "(none)|hi|hello"


def test_plan_pairwise_swap_and_pad() -> None:
    cases = [
        {
            "id": "c0",
            "input": "q",
            "observed_output": "one",
            "compare_output": "two",
            "expected_behavior": "e",
            "criteria": ["k"],
        },
        {"id": "c1", "input": "q", "observed_output": "x"},
    ]  # no compare_output: skipped
    rubric = {
        "criteria": [{"id": "k", "description": "d"}],
        "judges": [
            {"id": "p", "mode": "pairwise", "labels": ["A", "B"], "prompt": "{answer_a}|{answer_b}"}
        ],
    }
    rows = build_requests(cases, rubric, trials=1, probes=["swap", "pad"], probe_trials=1)
    by = {r["probe"]: r for r in rows}
    assert by["none"]["prompt"] == "one|two"
    assert by["swap"]["prompt"] == "two|one"
    assert by["pad"]["pad_side"] == "A" and by["pad"]["presented"]["answer_a"].endswith(PAD_TEXT)
    with pytest.raises(ValueError):
        build_requests(cases, rubric, probes=["shuffle"])


def test_run_is_off_by_default(ready_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_BUILDER_ENABLE_JUDGE_PLUGIN", raising=False)
    judge_plan(ready_workspace, trials=2)
    with pytest.raises(PluginDisabled):
        judge_run(ready_workspace, {"j1": "true"})
    assert not (ready_workspace / "judgments.jsonl").exists()


def test_run_with_command_and_resume(ready_workspace: Path, tmp_path: Path) -> None:
    script = tmp_path / "judge.py"
    script.write_text(ECHO_JUDGE)
    judge_plan(ready_workspace, trials=2)
    cmd = f"{sys.executable} {script}"
    log = judge_run(ready_workspace, {"j1": cmd}, enable=True)
    assert log["judges"]["j1"]["ok"] == 10 and log["judges"]["j1"]["errors"] == 0
    rows = [json.loads(x) for x in (ready_workspace / "judgments.jsonl").open()]
    assert len(rows) == 10 and {r["verdict"] for r in rows} == {"pass", "fail"}
    assert all(r["tokens"] == 3 and "prompt" not in r for r in rows)
    log = judge_run(ready_workspace, {"j1": cmd}, enable=True)  # resume: nothing left
    assert log["judges"]["j1"]["requests"] == 0


def test_run_reports_crashing_command(ready_workspace: Path, tmp_path: Path) -> None:
    script = tmp_path / "crash.py"
    script.write_text("import sys; sys.stdin.readline(); sys.exit(1)\n")
    judge_plan(ready_workspace, trials=1)
    log = judge_run(ready_workspace, {"j1": f"{sys.executable} {script}"}, enable=True)
    assert log["judges"]["j1"]["errors"] == 1
