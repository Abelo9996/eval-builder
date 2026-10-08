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
    "eval-builder turns an app's logs into an eval suite and checks LLM judges. It never "
    "calls a model: you write expected behavior and run the judge model. Workflow: "
    "ingest -> select -> draft -> list_cases, then update_case and set_rubric (fill expected "
    "behavior and criteria with the user) -> validate -> judge_plan -> run every request in "
    "judge_requests.jsonl through the judge model and append {request_id, verdict} lines to "
    "judgments.jsonl -> judge_check -> export -> report. Every tool takes `workspace` "
    "(default ./evalset). Never invent human labels; ask the user for them."
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
        """Step 1. Read log files or folders (OpenAI chat JSONL, Anthropic messages, Langfuse
        export, OpenTelemetry GenAI spans, or JSONL with input/output fields), normalize them
        into <workspace>/traces.jsonl and redact emails, keys, card, phone and SSN numbers.
        Format is detected per file; pass `format` only if detection fails. Tell the user the
        trace, skip and redaction counts. Next: select."""
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
        """Step 2. Pick `n` diverse, representative traces without an LLM: removes exact and
        near duplicates, clusters by topic, oversamples failures (errors, negative feedback)
        and covers every value of the `stratify` metadata keys (for example ["route"]).
        Each pick lists why it was picked. Next: draft."""
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
        """Step 3. Turn the selection into cases.yaml (input, earlier turns, logged output,
        TODO expected_behavior) and a rubric.yaml skeleton. Re-running keeps filled cases.
        Next: list_cases to read them, then update_case and set_rubric to fill them."""
        return draft_mod.draft(workspace, suite)

    @mcp.tool()
    def list_cases(workspace: str = "evalset", status: str | None = None) -> list[dict[str, Any]]:
        """Read the cases in cases.yaml (id, input, context, observed_output, expected_behavior,
        criteria, status), optionally filtered by status (draft, ready, dropped). Use this
        instead of parsing the YAML file yourself."""
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
        """Fill in or change one case. expected_behavior: one or two sentences on what a good
        answer does. criteria: ids defined in rubric.yaml (set_rubric). status: draft, ready
        (only after the expected behavior is checked) or dropped. Returns the updated case."""
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
        """Replace rubric.yaml. criteria: [{id, description, scale: pass_fail}].
        judges: [{id, mode: pointwise|pairwise, criteria: [ids], labels: [pass, fail] or
        [A, B], prompt, provider}]. The prompt may use {input}, {context}, {output},
        {expected_behavior}, {criteria} (pointwise) or {answer_a}, {answer_b} (pairwise).
        provider is optional: a promptfoo provider id for the judge model (for example
        ollama:chat:qwen2.5:7b-instruct); export uses it to wire a judge that passed
        judge_check into promptfoo. A prompt that answers JSON {"pass": true|false,
        "reason": "..."} works both here and in promptfoo. Returns validation errors."""
        return draft_mod.write_rubric(workspace, {"criteria": criteria, "judges": judges or []})

    @mcp.tool()
    def validate(workspace: str = "evalset") -> dict[str, Any]:
        """Check cases.yaml and rubric.yaml before judging or exporting. Lists every error
        (TODO left in a ready case, unknown criterion, judge without labels)."""
        return draft_mod.validate(workspace)

    @mcp.tool()
    def judge_plan(
        workspace: str = "evalset",
        judges: list[str] | None = None,
        trials: int = 5,
        probes: list[str] | None = None,
        probe_trials: int = 3,
    ) -> dict[str, Any]:
        """Step 5. Write judge_requests.jsonl: every judge call to make for the ready cases,
        repeated `trials` times, plus probes (swap: answer order, pairwise only; pad: an
        irrelevant paragraph appended). Each line has request_id, judge, case_id, labels and
        the rendered prompt. You then run each prompt through the judge model and append
        {"request_id": ..., "verdict": ...} lines to judgments.jsonl. Next: judge_check."""
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
        """Step 6. Read judgments.jsonl (and labels.jsonl, human labels as {"case_id",
        "label"}) and give each judge a verdict: trustworthy, unstable (flips across
        repeats), biased (answer order or padding moves it), misaligned (low kappa with
        humans) or not_enough_data. Summary rows carry 95% intervals and sample sizes;
        quote those. `next` says what to do next."""
        th = Thresholds(
            max_flip_rate=max_flip_rate,
            min_kappa=min_kappa,
            min_labeled=min_labeled,
            min_cases=min_cases,
        )
        r = judge_check_fn(workspace, judgments, labels, th)
        # per-case detail stays in judge_check_file; the summary has the numbers to quote
        return {k: v for k, v in r.items() if k != "judges"}

    @mcp.tool()
    def export(
        workspace: str = "evalset", formats: list[str] | None = None, judge: str | None = None
    ) -> dict[str, Any]:
        """Step 7. Export ready cases. formats: promptfoo, deepeval, inspect, jsonl (default
        all). promptfoo gets the full conversation as chat messages; a pointwise judge that
        passed judge_check and has a `provider` is wired in as the llm-rubric grader. `judge`
        forces a judge id (a warning says if it did not pass). Read `notes` in the result."""
        return export_fn(workspace, formats, judge)

    @mcp.tool()
    def report(workspace: str = "evalset", title: str | None = None) -> dict[str, Any]:
        """Last step. Write report.md and report.json covering every step that has run, with
        source hashes, selection reasons, the judge table and the limits."""
        return build_report(workspace, title)

    @mcp.tool()
    def status(workspace: str = "evalset") -> dict[str, Any]:
        """Which steps have run in this workspace and the next one to do. Call this first
        when resuming work in an existing workspace."""
        return status_fn(workspace)

    return mcp


def main() -> None:
    build_server().run("stdio")
