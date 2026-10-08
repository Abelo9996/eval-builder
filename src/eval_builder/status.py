"""Summarize which steps have run in a workspace and suggest the next one."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import Workspace


def status(workspace: str | Path) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    ready = 0
    if ws.cases.exists():
        from .draft import load_cases

        ready = sum(1 for c in load_cases(ws.root).get("cases") or [] if c.get("status") == "ready")
    steps: dict[str, Any] = {
        "ingest": ws.traces.exists(),
        "select": ws.selection.exists(),
        "draft": ws.cases.exists(),
        "cases_ready": ready,
        "judge_plan": ws.judge_requests.exists(),
        "judgments": ws.judgments.exists(),
        "label_sheet": ws.label_sheet_html.exists(),
        "labels": ws.labels.exists(),
        "judge_check": ws.judge_check.exists(),
        "export": (ws.exports / "manifest.json").exists(),
        "report": ws.report_md.exists(),
    }
    order = [
        ("ingest", "eval-builder ingest <logs>"),
        ("select", "eval-builder select -n 30"),
        ("draft", "eval-builder draft"),
        (
            "cases_ready",
            "fill expected_behavior and criteria per case and set status: ready "
            "(update_case or cases.yaml), add criteria and judges (set_rubric or rubric.yaml), "
            "then eval-builder validate",
        ),
        ("judge_plan", "eval-builder judge-plan --probes pad,swap (skip if you have no judges)"),
        (
            "judgments",
            "run each request in judge_requests.jsonl through the judge and append "
            "{request_id, verdict} lines to judgments.jsonl (or eval-builder judge-run)",
        ),
        (
            "labels",
            f"a person opens {ws.label_sheet_html} in a browser, labels the cases and exports "
            "labels.jsonl; then eval-builder label import <that file>"
            if steps["label_sheet"]
            else "eval-builder label (writes label_sheet.html for a person to label offline), "
            "then eval-builder label import <exported labels.jsonl>",
        ),
        ("judge_check", "eval-builder judge-check"),
        ("export", "eval-builder export"),
        ("report", "eval-builder report"),
    ]
    nxt = next((cmd for step, cmd in order if not steps[step]), "done")
    return {"workspace": str(ws.root), "steps": steps, "next": nxt}
