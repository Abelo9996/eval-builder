"""Summarize which steps have run in a workspace and suggest the next one."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import Workspace


def status(workspace: str | Path) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    steps = {
        "ingest": ws.traces.exists(),
        "select": ws.selection.exists(),
        "draft": ws.cases.exists(),
        "judge_plan": ws.judge_requests.exists(),
        "judgments": ws.judgments.exists(),
        "labels": ws.labels.exists(),
        "judge_check": ws.judge_check.exists(),
        "export": (ws.exports / "manifest.json").exists(),
        "report": ws.report_md.exists(),
    }
    order = [
        ("ingest", "eval-builder ingest <logs>"),
        ("select", "eval-builder select"),
        ("draft", "eval-builder draft"),
        ("export", "fill cases, then eval-builder export"),
        ("report", "eval-builder report"),
    ]
    nxt = next((cmd for step, cmd in order if not steps[step]), "done")
    return {"workspace": str(ws.root), "steps": steps, "next": nxt}
