"""Write case and rubric skeletons for the agent to fill in, and validate them.

The tool never writes expected behavior itself. It copies the observed input and
output from the selected traces and leaves TODO markers that validation refuses
to accept on cases marked `ready`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .ingest import load_traces
from .io import read_json, read_yaml, write_yaml
from .workspace import Workspace

STATUSES = ("draft", "ready", "dropped")
MODES = ("pointwise", "pairwise")
TODO = "TODO"

CASES_HEADER = """eval-builder case file. Fill in expected_behavior and criteria with the user,
then set status: ready (or dropped). Validation rejects ready cases that still
contain TODO. Criteria ids must exist in rubric.yaml.
Optional per case: reference_output (an ideal answer) and compare_output (a second
output for pairwise judging, for example from a new prompt version)."""

RUBRIC_HEADER = """eval-builder rubric. Define the criteria your cases reference and the judges
you plan to check. A judge prompt may use {input}, {context} (earlier turns), {output},
{answer_a}, {answer_b}, {expected_behavior} and {criteria}; judge-plan renders it per
request."""

UPDATABLE = (
    "expected_behavior",
    "criteria",
    "reference_output",
    "compare_output",
    "status",
    "notes",
    "tags",
)


def _rubric_skeleton() -> dict[str, Any]:
    return {
        "version": 1,
        "criteria": [
            {
                "id": "TODO-criterion-id",
                "description": "TODO: what must be true of a good answer",
                "scale": "pass_fail",
            },
        ],
        "judges": [
            {
                "id": "TODO-judge-id",
                "mode": "pointwise",
                "criteria": ["TODO-criterion-id"],
                "labels": ["pass", "fail"],
                "prompt": "TODO: the exact judge prompt. Use {input}, {output}, "
                "{expected_behavior}, {criteria}.",
            },
        ],
    }


def draft(
    workspace: str | Path, suite: str = "eval-builder suite", force: bool = False
) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    if not ws.selection.exists():
        raise FileNotFoundError(f"{ws.selection} not found; run `eval-builder select` first")
    selection = read_json(ws.selection)
    traces = {t.id: t for t in load_traces(ws.root)}
    existing: dict[str, Any] = {}
    if ws.cases.exists() and not force:
        existing = read_yaml(ws.cases) or {}
    cases = list(existing.get("cases") or [])
    known = {c.get("trace_id") for c in cases}
    next_num = len(cases) + 1
    added = 0
    for pick in selection["selected"]:
        tid = pick["trace_id"]
        if tid in known:
            continue
        t = traces.get(tid)
        if t is None:
            continue
        case: dict[str, Any] = {
            "id": f"case-{next_num:03d}",
            "trace_id": tid,
            "status": "draft",
            "selected_because": pick["reasons"],
            "input": t.input,
        }
        ctx = t.prior_turns()
        if ctx:
            case["context"] = ctx
        case["observed_output"] = t.output
        case["observed_failure"] = bool(pick.get("failure"))
        case["expected_behavior"] = f"{TODO}: one or two sentences on what a good answer does"
        case["criteria"] = ["TODO-criterion-id"]
        case["reference_output"] = None
        tags = []
        if t.route:
            tags.append(f"route:{t.route}")
        if t.model:
            tags.append(f"model:{t.model}")
        tags += [f"tool:{x}" for x in t.tools]
        if t.error:
            tags.append("error")
        if t.feedback:
            tags.append(f"feedback:{t.feedback}")
        tags.append(f"cluster:{pick['cluster']}")
        case["tags"] = tags
        cases.append(case)
        known.add(tid)
        next_num += 1
        added += 1
    doc = {"suite": existing.get("suite", suite), "version": 1, "cases": cases}
    write_yaml(ws.cases, doc, CASES_HEADER)
    rubric_created = False
    if not ws.rubric.exists() or force:
        write_yaml(ws.rubric, _rubric_skeleton(), RUBRIC_HEADER)
        rubric_created = True
    return {
        "cases_file": str(ws.cases),
        "rubric_file": str(ws.rubric),
        "cases_total": len(cases),
        "cases_added": added,
        "rubric_created": rubric_created,
        "next": "read the cases (list_cases, or cases.yaml), define criteria and judges "
        "(set_rubric, or rubric.yaml), fill expected_behavior and criteria per case and set "
        "status: ready (update_case), then run validate",
    }


def load_cases(workspace: str | Path) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    if not ws.cases.exists():
        raise FileNotFoundError(f"{ws.cases} not found; run `eval-builder draft` first")
    return read_yaml(ws.cases) or {"cases": []}


def load_rubric(workspace: str | Path) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    if not ws.rubric.exists():
        raise FileNotFoundError(f"{ws.rubric} not found; run `eval-builder draft` first")
    return read_yaml(ws.rubric) or {}


def _has_todo(v: Any) -> bool:
    if isinstance(v, str):
        return TODO in v
    if isinstance(v, list):
        return any(_has_todo(x) for x in v)
    if isinstance(v, dict):
        return any(_has_todo(x) for x in v.values())
    return False


def validate_rubric(rubric: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def err(where: str, problem: str) -> None:
        errors.append({"where": where, "problem": problem})

    crit = rubric.get("criteria") or []
    if not crit:
        err("rubric.criteria", "no criteria defined")
    seen: set[str] = set()
    for i, c in enumerate(crit):
        cid = str(c.get("id", ""))
        if not cid or _has_todo(cid):
            err(f"rubric.criteria[{i}].id", "missing or still TODO")
        if cid in seen:
            err(f"rubric.criteria[{i}].id", f"duplicate id {cid}")
        seen.add(cid)
        if not str(c.get("description", "")).strip() or _has_todo(c.get("description")):
            err(f"rubric.criteria[{i}].description", "missing or still TODO")
    judge_ids: set[str] = set()
    for i, j in enumerate(rubric.get("judges") or []):
        jid = str(j.get("id", ""))
        if not jid or _has_todo(jid):
            err(f"rubric.judges[{i}].id", "missing or still TODO")
        if jid in judge_ids:
            err(f"rubric.judges[{i}].id", f"duplicate id {jid}")
        judge_ids.add(jid)
        if j.get("mode", "pointwise") not in MODES:
            err(f"rubric.judges[{i}].mode", f"must be one of {', '.join(MODES)}")
        if not j.get("labels"):
            err(f"rubric.judges[{i}].labels", "list the verdict labels the judge may return")
        if _has_todo(j.get("prompt")):
            err(
                f"rubric.judges[{i}].prompt",
                "still TODO (remove the key if you run judges with your own prompt elsewhere)",
            )
        for cid in j.get("criteria") or []:
            if cid not in seen:
                err(f"rubric.judges[{i}].criteria", f"unknown criterion {cid}")
    return errors


def validate(workspace: str | Path) -> dict[str, Any]:
    doc = load_cases(workspace)
    rubric = load_rubric(workspace)
    errors = validate_rubric(rubric)
    crit_ids = {str(c.get("id")) for c in rubric.get("criteria") or []}
    counts = dict.fromkeys(STATUSES, 0)
    ids: set[str] = set()
    for i, c in enumerate(doc.get("cases") or []):
        cid = str(c.get("id", f"#{i}"))
        where = f"cases[{cid}]"
        if cid in ids:
            errors.append({"where": where, "problem": "duplicate case id"})
        ids.add(cid)
        status = c.get("status", "draft")
        if status not in STATUSES:
            errors.append({"where": where, "problem": f"status must be one of {STATUSES}"})
            continue
        counts[status] += 1
        if status != "ready":
            continue
        if not str(c.get("input", "")).strip():
            errors.append({"where": where, "problem": "empty input"})
        eb = c.get("expected_behavior")
        if not isinstance(eb, str) or not eb.strip() or _has_todo(eb):
            errors.append(
                {"where": f"{where}.expected_behavior", "problem": "missing or still TODO"}
            )
        crit = c.get("criteria") or []
        if not crit:
            errors.append({"where": f"{where}.criteria", "problem": "no criteria"})
        for k in crit:
            if k not in crit_ids:
                errors.append({"where": f"{where}.criteria", "problem": f"unknown criterion {k}"})
        if _has_todo(c.get("reference_output")):
            errors.append({"where": f"{where}.reference_output", "problem": "still TODO"})
    if counts["ready"] == 0:
        errors.append({"where": "cases", "problem": "no cases have status: ready"})
    warnings = []
    if counts["draft"]:
        warnings.append(f"{counts['draft']} case(s) still draft; they are not exported")
    return {"valid": not errors, "counts": counts, "errors": errors, "warnings": warnings}


def update_case(workspace: str | Path, case_id: str, **fields: Any) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    doc = load_cases(ws.root)
    bad = [k for k in fields if k not in UPDATABLE]
    if bad:
        raise ValueError(f"cannot update {bad}; allowed: {', '.join(UPDATABLE)}")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    for c in doc.get("cases") or []:
        if c.get("id") == case_id:
            for k, v in fields.items():
                if v is not None:
                    c[k] = v
            write_yaml(ws.cases, doc, CASES_HEADER)
            return c
    raise KeyError(f"no case with id {case_id}")


def write_rubric(workspace: str | Path, rubric: dict[str, Any]) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    rubric = {"version": 1, **rubric}
    write_yaml(ws.rubric, rubric, RUBRIC_HEADER)
    return {"rubric_file": str(ws.rubric), "errors": validate_rubric(rubric)}


def ready_cases(workspace: str | Path) -> list[dict[str, Any]]:
    return [c for c in load_cases(workspace).get("cases") or [] if c.get("status") == "ready"]
