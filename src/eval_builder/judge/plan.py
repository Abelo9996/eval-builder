"""Build the list of judge calls (with probes) that someone has to run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..draft import load_rubric, ready_cases
from ..io import write_jsonl
from ..workspace import Workspace

PROBES = ("swap", "pad")

# What each line of judge_requests.jsonl holds, so whoever runs the judge does not guess.
REQUEST_FIELDS = {
    "request_id": "unique id; copy it into the judgment row",
    "judge": "judge id from rubric.yaml (which model or prompt to use)",
    "case_id": "case in cases.yaml",
    "mode": "pointwise or pairwise",
    "probe": "none, swap (answers trade places) or pad (irrelevant paragraph appended)",
    "trial": "repeat number; use the same prompt and settings for every trial",
    "labels": "allowed verdicts",
    "prompt": "the rendered judge prompt to send (null if the judge has no prompt template)",
    "presented": "the fields that were filled into the prompt",
}

# Deliberately irrelevant filler for the verbosity probe. It adds length without
# adding anything that answers the question, so a judge's verdict should not move.
PAD_TEXT = (
    "Additional background: The metric system was first adopted in France in 1795, and "
    "the meter was originally defined as one ten-millionth of the distance from the equator "
    "to the North Pole along a meridian. Over the following two centuries most countries "
    "adopted it for trade and science. Standard units have been redefined several times, "
    "most recently in 2019, when the kilogram, ampere, kelvin and mole were tied to fixed "
    "values of physical constants. Many everyday objects, from paper sizes to bottle volumes, "
    "follow metric conventions. This background is provided for completeness."
)


def pad(text: str) -> str:
    return f"{text.rstrip()}\n\n{PAD_TEXT}"


def render(template: str | None, fields: dict[str, str]) -> str | None:
    if not template:
        return None
    out = template
    for k, v in fields.items():
        out = out.replace("{" + k + "}", v)
    return out


def _presented(case: dict[str, Any], mode: str, probe: str, pad_side: str | None) -> dict[str, str]:
    inp = str(case.get("input", ""))
    out = str(case.get("observed_output") or "")
    if mode == "pointwise":
        return {"input": inp, "output": pad(out) if probe == "pad" else out}
    a, b = out, str(case.get("compare_output") or "")
    if probe == "pad":
        if pad_side == "A":
            a = pad(a)
        else:
            b = pad(b)
    if probe == "swap":
        a, b = b, a
    return {"input": inp, "answer_a": a, "answer_b": b}


def build_requests(
    cases: list[dict[str, Any]],
    rubric: dict[str, Any],
    judges: list[str] | None = None,
    trials: int = 5,
    probes: list[str] | None = None,
    probe_trials: int = 3,
) -> list[dict[str, Any]]:
    if trials < 1 or probe_trials < 1:
        raise ValueError("trials and probe_trials must be >= 1")
    probes = list(probes or [])
    for p in probes:
        if p not in PROBES:
            raise ValueError(f"unknown probe {p!r}; expected one of {PROBES}")
    all_judges = {str(j.get("id", "")): j for j in rubric.get("judges") or []}
    if not all_judges:
        raise ValueError(
            "rubric.yaml defines no judges; add one with set_rubric (MCP) or edit rubric.yaml: "
            "{id, mode: pointwise|pairwise, labels: [pass, fail], prompt: '...{input}...{output}'}"
        )
    chosen = judges or list(all_judges)
    missing = [j for j in chosen if j not in all_judges]
    if missing:
        raise ValueError(f"judges not in rubric.yaml: {missing}; known: {sorted(all_judges)}")
    todo = [j for j in chosen if "TODO" in j or "TODO" in str(all_judges[j].get("prompt") or "")]
    if todo:
        raise ValueError(
            f"judge(s) {todo} in rubric.yaml still have a TODO id or prompt; write the real "
            "judge id and prompt first (run validate to see every problem)"
        )
    if not cases:
        raise ValueError(
            "no cases have status: ready, so there is nothing to judge; fill expected_behavior "
            "and criteria, set status: ready (update_case), then run validate"
        )
    crit_desc = {c["id"]: c.get("description", "") for c in rubric.get("criteria") or []}
    rows: list[dict[str, Any]] = []
    for jid in chosen:
        judge = all_judges[jid]
        mode = judge.get("mode", "pointwise")
        for ci, case in enumerate(cases):
            if mode == "pairwise" and not case.get("compare_output"):
                continue
            criteria = [c for c in case.get("criteria") or [] if c in crit_desc]
            criteria_text = "\n".join(f"- {c}: {crit_desc[c]}" for c in criteria)
            context_text = (
                "\n\n".join(
                    f"{m.get('role', 'user')}: {m.get('content', '')}"
                    for m in case.get("context") or []
                )
                or "(none)"
            )
            # swap only makes sense for pairwise judges
            plan = [("none", trials)] + [
                (p, probe_trials) for p in probes if not (p == "swap" and mode != "pairwise")
            ]
            for probe, n in plan:
                pad_side = None
                if probe == "pad":
                    pad_side = "output" if mode == "pointwise" else ("A" if ci % 2 == 0 else "B")
                shown = _presented(case, mode, probe, pad_side)
                fields = {
                    **shown,
                    "context": context_text,
                    "expected_behavior": str(case.get("expected_behavior", "")),
                    "criteria": criteria_text,
                }
                for t in range(n):
                    rows.append(
                        {
                            "request_id": f"{jid}:{case['id']}:{probe}:{t}",
                            "judge": jid,
                            "case_id": case["id"],
                            "mode": mode,
                            "probe": probe,
                            "trial": t,
                            "pad_side": pad_side,
                            "labels": judge.get("labels") or [],
                            "presented": shown,
                            "expected_behavior": case.get("expected_behavior"),
                            "criteria": criteria,
                            "prompt": render(judge.get("prompt"), fields),
                        }
                    )
    return rows


def judge_plan(
    workspace: str | Path,
    judges: list[str] | None = None,
    trials: int = 5,
    probes: list[str] | None = None,
    probe_trials: int = 3,
) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    rows = build_requests(
        ready_cases(ws.root), load_rubric(ws.root), judges, trials, probes, probe_trials
    )
    write_jsonl(ws.judge_requests, rows)
    per_judge: dict[str, int] = {}
    for r in rows:
        per_judge[r["judge"]] = per_judge.get(r["judge"], 0) + 1
    skipped_pairwise = [
        jid
        for jid in (judges or [str(j.get("id")) for j in load_rubric(ws.root).get("judges") or []])
        if jid not in per_judge
    ]
    out: dict[str, Any] = {
        "requests_file": str(ws.judge_requests),
        "judgments_file": str(ws.judgments),
        "requests": len(rows),
        "per_judge": per_judge,
        "request_fields": REQUEST_FIELDS,
        "verdict_row": '{"request_id": "<from the request>", "verdict": "<one of labels>"}',
        "next": (
            f"for each line of {ws.judge_requests.name}: send `prompt` to the model named by "
            f"`judge` and append one JSON line {{request_id, verdict}} to {ws.judgments.name} "
            "(verdict: the judge's answer, as a label from `labels`, raw text or the "
            "judge's JSON). Or let eval-builder drive your judge script: `eval-builder judge-run "
            '--enable-judge-plugin --command "<judge>=<your command>"`. Then run judge_check.'
        ),
    }
    if skipped_pairwise:
        out["warnings"] = [
            f"judge {j} produced no requests: pairwise judges need cases with compare_output"
            for j in skipped_pairwise
        ]
    return out
