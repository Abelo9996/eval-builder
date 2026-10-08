"""Command line interface. Every command accepts --json for machine-readable output."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__


def _csv(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _print(result: Any, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(human)


def _cmd_ingest(a: argparse.Namespace) -> int:
    from .ingest import ingest

    r = ingest(a.paths, a.workspace, a.format, redact=not a.no_redact)
    lines = [f"ingested {r['traces']} traces into {r['output_file']}"]
    for s in r["sources"]:
        skipped = sum(s["skipped"].values())
        lines.append(
            f"  {s['path']}: format={s['format']} records={s['records']} "
            f"traces={s['traces']} skipped={skipped} sha256={s['sha256'][:16]}"
        )
    red = r["redactions"]
    lines.append(
        f"redactions: {red['total']} "
        + (str(red["by_kind"]) if red["enabled"] else "(redaction off)")
    )
    lines.append("next: eval-builder select -n 30 (add --stratify <metadata keys> to cover them)")
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_select(a: argparse.Namespace) -> int:
    from .select import select

    r = select(
        a.workspace,
        n=a.n,
        seed=a.seed,
        clusters=a.clusters,
        failure_share=a.failure_share,
        near_dup_threshold=a.near_dup,
        dedupe_on=a.dedupe_on,
        stratify=_csv(a.stratify),
    )
    p = r["population"]
    lines = [
        f"{p['traces']} traces -> {p['unique']} unique "
        f"({p['exact_duplicates_removed']} exact dupes, {p['near_duplicates_merged']} near "
        f"dupes) -> selected {r['selected_count']} ({r['selected_failures']} failures) "
        f"across {r['params']['clusters']} clusters"
    ]
    for s in r["selected"][:10]:
        lines.append(f"  {s['trace_id']}: {s['reasons'][0]}")
    if r["selected_count"] > 10:
        lines.append(f"  ... {r['selected_count'] - 10} more in selection.json")
    lines += [f"note: {x}" for x in r.get("notes", [])]
    lines.append(f"next: {r['next']}")
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_draft(a: argparse.Namespace) -> int:
    from .draft import draft

    r = draft(a.workspace, a.suite, force=a.force)
    _print(
        r,
        a.json,
        f"{r['cases_added']} case(s) added, {r['cases_total']} total in "
        f"{r['cases_file']}\nnext: {r['next']}",
    )
    return 0


def _cmd_validate(a: argparse.Namespace) -> int:
    from .draft import validate

    r = validate(a.workspace)
    lines = [("valid" if r["valid"] else "INVALID") + f": {r['counts']}"]
    lines += [f"  error {e['where']}: {e['problem']}" for e in r["errors"][:30]]
    lines += [f"  warning: {w}" for w in r["warnings"]]
    _print(r, a.json, "\n".join(lines))
    return 0 if r["valid"] else 1


def _cmd_judge_plan(a: argparse.Namespace) -> int:
    from .judge.plan import judge_plan

    r = judge_plan(a.workspace, _csv(a.judges), a.trials, _csv(a.probes), a.probe_trials)
    lines = [f"{r['requests']} judge requests in {r['requests_file']} {r['per_judge']}"]
    lines += [f"warning: {w}" for w in r.get("warnings", [])]
    lines.append(f"next: {r['next']}")
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_judge_run(a: argparse.Namespace) -> int:
    from .judge.run import PluginDisabled, judge_run

    commands = {}
    for spec in a.command:
        if "=" not in spec:
            print(f"--command must look like judge_id=command, got {spec!r}", file=sys.stderr)
            return 2
        jid, cmd = spec.split("=", 1)
        commands[jid.strip()] = cmd.strip()
    try:
        r = judge_run(
            a.workspace,
            commands,
            enable=a.enable_judge_plugin,
            timeout=a.timeout,
            resume=not a.restart,
        )
    except PluginDisabled as e:
        print(str(e), file=sys.stderr)
        return 3
    lines = [
        f"{jid}: {e['ok']} ok, {e['errors']} errors, {e['seconds']} s"
        for jid, e in r["judges"].items()
    ]
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_judge_check(a: argparse.Namespace) -> int:
    from .judge.check import Thresholds, judge_check

    th = Thresholds(
        min_trials=a.min_trials,
        min_cases=a.min_cases,
        max_flip_rate=a.max_flip_rate,
        min_position_consistency=a.min_position_consistency,
        max_toward_padded_rate=a.max_toward_padded,
        min_kappa=a.min_kappa,
        min_labeled=a.min_labeled,
    )
    r = judge_check(a.workspace, a.judgments, a.labels, th)
    lines = []
    for s in r["summary"]:

        def f(x: float | None) -> str:
            return "n/a" if x is None else f"{x:.2f}"

        lines.append(
            f"{s['judge']:<28} {s['verdict']:<16} flip={f(s['flip_rate'])} "
            f"kappa={f(s['kappa'])} acc={f(s['accuracy'])} "
            f"pos={f(s['position_consistency'])} pad={f(s['toward_padded'])}"
        )
        lines += [f"    {x}" for x in s["reasons"]]
    lines.append(f"next: {r['next']}")
    out = {k: v for k, v in r.items() if k != "judges"} if not a.full else r
    _print(out, a.json, "\n".join(lines))
    return 0


def _cmd_export(a: argparse.Namespace) -> int:
    from .export import export

    r = export(a.workspace, _csv(a.formats), a.judge)
    if not r["exported"]:
        errs = r["validation"]["errors"]
        lines = ["not exported: validation failed"] + [
            f"  {e['where']}: {e['problem']}" for e in errs[:30]
        ]
        _print(r, a.json, "\n".join(lines))
        return 1
    lines = [f"exported {r['cases']} cases"] + [f"  {f['path']}" for f in r["files"]]
    g = r.get("promptfoo_grader")
    if g:
        prov = g["provider"]["id"] if isinstance(g["provider"], dict) else g["provider"]
        lines.append(f"promptfoo grader: judge {g['judge']} ({prov}), verdict {g['verdict']}")
    lines += [f"note: {n}" for n in r.get("notes", [])]
    lines.append(f"next: {r['next']}")
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_report(a: argparse.Namespace) -> int:
    from .report import build_report

    r = build_report(a.workspace, a.title)
    _print(r, a.json, f"wrote {r['report_md']} and {r['report_json']}")
    return 0


def _cmd_status(a: argparse.Namespace) -> int:
    from .status import status

    r = status(a.workspace)
    lines = [
        f"{k}: {v}"
        if isinstance(v, int) and not isinstance(v, bool)
        else f"{k}: {'done' if v else '-'}"
        for k, v in r["steps"].items()
    ]
    lines.append(f"next: {r['next']}")
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_setup(a: argparse.Namespace) -> int:
    from .setup_agents import setup

    server = a.server_command.split() if a.server_command else None
    r = setup(yes=a.yes, server=server)
    lines = []
    for act in r["actions"]:
        lines.append(f"[{act['agent']}] {act['kind']}: {act['target']}")
        lines.append(f"    {act['detail'].strip()}")
        if "result" in act:
            lines.append(f"    -> {act['result']}")
    lines.append(("applied. next: " if r["applied"] else "") + r["next"])
    _print(r, a.json, "\n".join(lines))
    return 0


def _cmd_mcp(a: argparse.Namespace) -> int:
    from .mcp_server import main

    main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval-builder",
        description="Turn real LLM app logs into an eval suite and check which LLM judges you "
        "can trust. Runs locally; never calls a model provider.",
    )
    p.add_argument("--version", action="version", version=f"eval-builder {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name: str, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.add_argument(
            "-w", "--workspace", default="evalset", help="workspace directory (default: ./evalset)"
        )
        sp.add_argument("--json", action="store_true", help="print JSON")
        return sp

    s = cmd("ingest", "Read and normalize traces, redacting secrets and PII by default.")
    s.add_argument("paths", nargs="+", help="log files or directories (.json, .jsonl)")
    s.add_argument(
        "-f",
        "--format",
        choices=["openai", "anthropic", "langfuse", "otel", "generic"],
        help="force a format (default: detect per file)",
    )
    s.add_argument("--no-redact", action="store_true", help="keep emails, keys and numbers as-is")
    s.set_defaults(func=_cmd_ingest)

    s = cmd("select", "Pick a diverse, representative set of traces without an LLM.")
    s.add_argument("-n", type=int, default=50, help="number of cases to pick (default 50)")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--clusters", type=int, help="k for k-means (default: sqrt of unique traces)")
    s.add_argument(
        "--failure-share",
        type=float,
        default=0.3,
        help="share of the budget reserved for errors and negative feedback",
    )
    s.add_argument(
        "--near-dup",
        type=float,
        default=0.9,
        help="cosine threshold for near-duplicates (default 0.9)",
    )
    s.add_argument("--dedupe-on", choices=["input", "input+output"], default="input")
    s.add_argument("--stratify", help="extra metadata keys to cover, comma separated")
    s.set_defaults(func=_cmd_select)

    s = cmd("draft", "Write cases.yaml and rubric.yaml skeletons for the agent to fill in.")
    s.add_argument("--suite", default="eval-builder suite", help="suite name")
    s.add_argument("--force", action="store_true", help="overwrite existing cases and rubric")
    s.set_defaults(func=_cmd_draft)

    s = cmd("validate", "Check cases.yaml and rubric.yaml.")
    s.set_defaults(func=_cmd_validate)

    s = cmd("judge-plan", "List every judge call to make, with repeats and bias probes.")
    s.add_argument("--judges", help="judge ids from rubric.yaml, comma separated (default all)")
    s.add_argument("--trials", type=int, default=5, help="repeats per case (default 5)")
    s.add_argument("--probes", help="comma separated: swap (pairwise only), pad")
    s.add_argument("--probe-trials", type=int, default=3, help="repeats per probe (default 3)")
    s.set_defaults(func=_cmd_judge_plan)

    s = cmd("judge-run", "Run judge requests through YOUR command (off by default).")
    s.add_argument(
        "--command",
        action="append",
        required=True,
        help="judge_id=command; the command reads JSON lines on stdin and writes "
        '{"verdict": ...} lines on stdout. Repeat per judge.',
    )
    s.add_argument(
        "--enable-judge-plugin",
        action="store_true",
        help="required: allow eval-builder to start the judge command",
    )
    s.add_argument("--timeout", type=float, default=120.0, help="seconds per request")
    s.add_argument("--restart", action="store_true", help="discard existing judgments.jsonl")
    s.set_defaults(func=_cmd_judge_run)

    s = cmd("judge-check", "Measure judge stability, human agreement and bias.")
    s.add_argument("--judgments", help="judgments file (default: <workspace>/judgments.jsonl)")
    s.add_argument("--labels", help="human labels file (default: <workspace>/labels.jsonl)")
    s.add_argument("--min-trials", type=int, default=3)
    s.add_argument("--min-cases", type=int, default=10)
    s.add_argument("--max-flip-rate", type=float, default=0.2)
    s.add_argument("--min-position-consistency", type=float, default=0.8)
    s.add_argument("--max-toward-padded", type=float, default=0.1)
    s.add_argument("--min-kappa", type=float, default=0.4)
    s.add_argument("--min-labeled", type=int, default=20)
    s.add_argument("--full", action="store_true", help="include per-case detail in --json output")
    s.set_defaults(func=_cmd_judge_check)

    s = cmd("export", "Export ready cases for promptfoo, DeepEval, Inspect AI and JSONL.")
    s.add_argument("--formats", help="comma separated (default: promptfoo,deepeval,inspect,jsonl)")
    s.add_argument(
        "--judge",
        help="rubric.yaml judge to wire into promptfoo as the grader (default: the first "
        "pointwise judge that passed judge-check and has a provider)",
    )
    s.set_defaults(func=_cmd_export)

    s = cmd("report", "Write report.md and report.json.")
    s.add_argument("--title", help="report title")
    s.set_defaults(func=_cmd_report)

    s = cmd("status", "Show which steps have run.")
    s.set_defaults(func=_cmd_status)

    s = sub.add_parser("setup", help="Register the MCP server with Claude Code, Codex, Cursor.")
    s.add_argument("--yes", action="store_true", help="apply the changes (default: show them)")
    s.add_argument("--server-command", help='server command (default: "uvx eval-builder mcp")')
    s.add_argument("--json", action="store_true", help="print JSON")
    s.set_defaults(func=_cmd_setup)

    s = sub.add_parser("mcp", help="Run the MCP server over stdio.")
    s.set_defaults(func=_cmd_mcp)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, ValueError, KeyError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        if getattr(args, "json", False):
            print(json.dumps({"error": str(msg)}))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
