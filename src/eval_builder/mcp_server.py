"""MCP server (stdio). Every tool returns the same JSON the CLI prints with --json.

The opt-in judge runner is deliberately not exposed here: it executes a command,
which should stay an explicit CLI action by the user.
"""

from __future__ import annotations

from typing import Any

from . import draft as draft_mod
from .export import export as export_fn
from .ingest import ingest as ingest_fn
from .judge.check import Thresholds
from .judge.check import judge_check as judge_check_fn
from .judge.plan import judge_plan as judge_plan_fn
from .report import build_report
from .select import select as select_fn
from .status import status as status_fn

INSTRUCTIONS = (
    "eval-builder turns an app's logs into an eval suite and checks LLM judges. Workflow: "
    "ingest -> select -> draft (you fill expected_behavior and criteria with the user, via "
    "update_case and set_rubric) -> validate -> judge_plan (run each request several times "
    "with the user's judge, save judgments.jsonl) -> judge_check -> export -> report. "
    "Never invent human labels; ask the user for them."
)


def _server() -> Any:
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer("eval-builder", instructions=INSTRUCTIONS)
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]  # mcp 1.x

        return FastMCP("eval-builder", instructions=INSTRUCTIONS)


def build_server() -> Any:
    mcp = _server()

    @mcp.tool()
    def ingest(
        paths: list[str], workspace: str = "evalset", format: str | None = None, redact: bool = True
    ) -> dict[str, Any]:
        """Read traces (OpenAI chat JSONL, Anthropic messages, Langfuse export, OpenTelemetry
        GenAI spans, or generic input/output JSONL), normalize and redact them."""
        return ingest_fn(paths, workspace, format, redact)

    @mcp.tool()
    def select(
        workspace: str = "evalset",
        n: int = 50,
        seed: int = 0,
        clusters: int | None = None,
        failure_share: float = 0.3,
        near_dup_threshold: float = 0.9,
        dedupe_on: str = "input",
        stratify: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pick a diverse, representative set of traces and record why each was picked."""
        r = select_fn(
            workspace, n, seed, clusters, failure_share, near_dup_threshold, dedupe_on, stratify
        )
        return {k: v for k, v in r.items() if k != "selected"} | {
            "selected": [
                {"trace_id": s["trace_id"], "reasons": s["reasons"]} for s in r["selected"]
            ]
        }

    @mcp.tool()
    def draft(workspace: str = "evalset", suite: str = "eval-builder suite") -> dict[str, Any]:
        """Write cases.yaml and rubric.yaml skeletons from the selection (keeps filled cases)."""
        return draft_mod.draft(workspace, suite)

    @mcp.tool()
    def list_cases(workspace: str = "evalset", status: str | None = None) -> list[dict[str, Any]]:
        """Return the cases in cases.yaml, optionally filtered by status."""
        cases = draft_mod.load_cases(workspace).get("cases") or []
        return [c for c in cases if status is None or c.get("status") == status]

    @mcp.tool()
    def update_case(
        case_id: str,
        workspace: str = "evalset",
        expected_behavior: str | None = None,
        criteria: list[str] | None = None,
        reference_output: str | None = None,
        compare_output: str | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Fill in or change one case. status is draft, ready or dropped."""
        fields = {
            "expected_behavior": expected_behavior,
            "criteria": criteria,
            "reference_output": reference_output,
            "compare_output": compare_output,
            "status": status,
            "notes": notes,
        }
        return draft_mod.update_case(
            workspace, case_id, **{k: v for k, v in fields.items() if v is not None}
        )

    @mcp.tool()
    def set_rubric(
        criteria: list[dict[str, Any]],
        judges: list[dict[str, Any]] | None = None,
        workspace: str = "evalset",
    ) -> dict[str, Any]:
        """Replace rubric.yaml. criteria: [{id, description, scale}]. judges: [{id, mode
        (pointwise|pairwise), criteria, labels, prompt}]."""
        return draft_mod.write_rubric(workspace, {"criteria": criteria, "judges": judges or []})

    @mcp.tool()
    def validate(workspace: str = "evalset") -> dict[str, Any]:
        """Check cases.yaml and rubric.yaml; ready cases must have no TODO left."""
        return draft_mod.validate(workspace)

    @mcp.tool()
    def judge_plan(
        workspace: str = "evalset",
        judges: list[str] | None = None,
        trials: int = 5,
        probes: list[str] | None = None,
        probe_trials: int = 3,
    ) -> dict[str, Any]:
        """Write judge_requests.jsonl: every judge call to make, repeated `trials` times, plus
        optional probes (swap: answer order, pairwise only; pad: irrelevant length)."""
        return judge_plan_fn(workspace, judges, trials, probes, probe_trials)

    @mcp.tool()
    def judge_check(
        workspace: str = "evalset",
        judgments: str | None = None,
        labels: str | None = None,
        max_flip_rate: float = 0.2,
        min_kappa: float = 0.4,
        min_labeled: int = 20,
        min_cases: int = 10,
    ) -> dict[str, Any]:
        """Flip rate, human agreement (accuracy, kappa), position and verbosity probes, and a
        verdict per judge: trustworthy, unstable, biased, misaligned or not_enough_data."""
        th = Thresholds(
            max_flip_rate=max_flip_rate,
            min_kappa=min_kappa,
            min_labeled=min_labeled,
            min_cases=min_cases,
        )
        r = judge_check_fn(workspace, judgments, labels, th)
        return {k: v for k, v in r.items() if k != "judges"}

    @mcp.tool()
    def export(workspace: str = "evalset", formats: list[str] | None = None) -> dict[str, Any]:
        """Export ready cases to promptfoo, deepeval, inspect and/or jsonl."""
        return export_fn(workspace, formats)

    @mcp.tool()
    def report(workspace: str = "evalset", title: str | None = None) -> dict[str, Any]:
        """Write report.md and report.json covering every step that has run."""
        return build_report(workspace, title)

    @mcp.tool()
    def status(workspace: str = "evalset") -> dict[str, Any]:
        """Which steps have run in this workspace and what to do next."""
        return status_fn(workspace)

    return mcp


def main() -> None:
    build_server().run("stdio")
