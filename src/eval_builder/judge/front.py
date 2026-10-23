"""`judge-check <judge>`: the one-command front door.

Point it at a model (ollama:..., openai:..., anthropic:..., claude-code, codex) and it
builds cases (a bundled human-labeled sample, or your own --logs), runs the judge over
them with the bias and stability probes, and prints a one-screen verdict plus a shareable
reliability card. No rubric to write, no adapter, no labels required for the probes.

This is the only part of eval-builder that calls a model. It still ships no keys and
runs local models for free; paid APIs need --yes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..io import read_json, write_json, write_jsonl
from ..workspace import Workspace
from . import card as card_mod
from .backends import Backend, ollama_loaded, ollama_unload, parse_spec, preflight
from .check import Thresholds, check_judge
from .plan import build_requests
from .sample import load_sample

PAIRWISE_PROMPT = """You are comparing two AI assistant answers to the same user question. \
Judge which answer is better overall: more helpful, relevant, accurate, and detailed.

[User question]
{input}

[Answer A]
{answer_a}

[Answer B]
{answer_b}

Respond with ONLY a single character: A if Answer A is better, or B if Answer B is \
better. No words, no punctuation, no explanation."""

POINTWISE_PROMPT = """You are a strict grader. Decide whether the AI assistant's answer is a \
good response to the user's request: helpful, relevant, accurate, and appropriately detailed.

[User request]
{input}

[Answer]
{output}

Respond with ONLY one word: pass or fail. No explanation."""

Progress = Callable[[int, int], None]


def _cases_from_logs(
    workspace: Workspace, logs: list[str], n: int, fmt: str | None
) -> list[dict[str, Any]]:
    from ..ingest import ingest, load_traces
    from ..select import select

    ingest(logs, workspace.root, fmt, redact=True)
    select(workspace.root, n=n)
    selection = read_json(workspace.selection)
    traces = {t.id: t for t in load_traces(workspace.root)}
    cases: list[dict[str, Any]] = []
    for i, pick in enumerate(selection["selected"], 1):
        t = traces.get(pick["trace_id"])
        if t is None or not str(t.output).strip():
            continue
        case: dict[str, Any] = {
            "id": f"case-{i:03d}",
            "trace_id": t.id,
            "status": "ready",
            "input": t.input,
            "observed_output": t.output,
            "expected_behavior": "A good answer is helpful, relevant, accurate and "
            "appropriately detailed for the user's request.",
            "criteria": ["overall-quality"],
        }
        ctx = t.prior_turns()
        if ctx:
            case["context"] = ctx
        cases.append(case)
    return cases


def build_plan(
    spec: str,
    *,
    logs: list[str] | None = None,
    prompt_file: str | None = None,
    pairs: int = 20,
    trials: int = 5,
    probe_trials: int = 3,
    base_url: str | None = None,
    temperature: float = 0.7,
    workspace: str | Path = "judgecheck",
    backend: Backend | None = None,
    fmt: str | None = None,
) -> dict[str, Any]:
    """Resolve the backend and build every judge request. No model is called here."""
    b = backend or parse_spec(spec, base_url=base_url, temperature=temperature)
    ws = Workspace.at(workspace).ensure()
    labels: dict[str, str]
    if logs:
        cases = _cases_from_logs(ws, logs, pairs, fmt)
        mode, probes = "pointwise", ["pad"]
        labels = {}
        source = {"source": "logs", "citation": None, "paths": logs}
    else:
        cases, labels, source = load_sample(pairs)
        mode, probes = "pairwise", ["swap", "pad"]
    if not cases:
        raise ValueError("no usable cases were built (every candidate had an empty answer)")
    prompt = (
        Path(prompt_file).read_text(encoding="utf-8")
        if prompt_file
        else (PAIRWISE_PROMPT if mode == "pairwise" else POINTWISE_PROMPT)
    )
    rubric = {
        "version": 1,
        "criteria": [
            {"id": "overall-quality", "description": "overall answer quality", "scale": "pass_fail"}
        ],
        "judges": [
            {
                "id": b.id,
                "mode": mode,
                "criteria": ["overall-quality"],
                "labels": ["A", "B"] if mode == "pairwise" else ["pass", "fail"],
                "prompt": prompt,
            }
        ],
    }
    requests = build_requests(cases, rubric, [b.id], trials, probes, probe_trials)
    return {
        "backend": b,
        "workspace": ws,
        "cases": cases,
        "labels": labels,
        "mode": mode,
        "prompt": prompt,
        "prompt_hash": sha256(prompt.encode()).hexdigest()[:12],
        "requests": requests,
        "source": source,
        "probes": probes,
        "trials": trials,
        "probe_trials": probe_trials,
    }


def _run_requests(
    backend: Backend, requests: list[dict[str, Any]], progress: Progress | None
) -> tuple[list[dict[str, Any]], int]:
    from .backends import BackendError

    rows: list[dict[str, Any]] = []
    errors = 0
    total = len(requests)
    for i, r in enumerate(requests, 1):
        row = {k: v for k, v in r.items() if k not in ("presented", "prompt")}
        try:
            raw = backend(r["prompt"], int(r.get("trial", 0)))
            row["verdict"] = raw
            row["raw"] = raw
        except BackendError as e:
            row["verdict"] = None
            row["error"] = str(e)
            errors += 1
        rows.append(row)
        if progress:
            progress(i, total)
    return rows, errors


def _ci(d: dict[str, Any] | None) -> str:
    ci = (d or {}).get("ci95")
    if not ci:
        return ""
    return f"CI {ci[0] * 100:.0f} to {ci[1] * 100:.0f}%"


def _worst(statuses: list[str]) -> str:
    for level in ("critical", "warning", "good"):
        if level in statuses:
            return level
    return "good"


def _band(value: float, good: float, warn: float) -> str:
    return "good" if value <= good else "warning" if value <= warn else "critical"


def build_meters(j: dict[str, Any], mode: str) -> tuple[list[card_mod.Meter], list[str]]:
    """Turn one judge's check result into card meters and the sentences for the headline."""
    meters: list[card_mod.Meter] = []
    sentences: list[str] = []

    st = j["stability"]
    fr = st["flip_rate"]["rate"] or 0.0
    status = _band(fr, 0.2, 0.4)
    meters.append(
        card_mod.Meter("Flips on identical repeats", fr, status, f"{fr:.0%}", _ci(st["flip_rate"]))
    )
    sentences.append(f"flips on {fr:.0%} of identical repeats")

    pos = j.get("position_probe")
    if pos and pos["cases"]:
        fp = pos["first_position_rate"]["rate"] or 0.0
        follow = max(fp, 1 - fp)
        side = "first-shown" if fp >= 0.5 else "second-shown"
        status = _band(abs(fp - 0.5), 0.1, 0.2)
        ci = pos["first_position_rate"].get("ci95")
        if ci and fp < 0.5:  # bar measures the second-shown share, so flip the interval
            ci = [1 - ci[1], 1 - ci[0]]
        ci_text = f"CI {ci[0] * 100:.0f} to {ci[1] * 100:.0f}%" if ci else ""
        meters.append(
            card_mod.Meter(f"Follows the {side} answer", follow, status, f"{follow:.0%}", ci_text)
        )
        sentences.append(f"follows the {side} answer {follow:.0%} of the time")

    ver = j.get("verbosity_probe")
    if ver and ver["cases"]:
        tp = ver["toward_padded"]["rate"] or 0.0
        status = _band(tp, 0.1, 0.25)
        meters.append(
            card_mod.Meter(
                "Prefers the padded answer", tp, status, f"{tp:.0%}", _ci(ver["toward_padded"])
            )
        )
        sentences.append(f"prefers the padded answer {tp:.0%} of the time")

    ag = j.get("human_agreement")
    if ag and ag["cases"]:
        kappa = ag["kappa"]
        acc = ag["accuracy"]["rate"]
        if kappa is None:
            status, pct, vtext = "critical", 0.0, "kappa n/a"
        else:
            status = "good" if kappa >= 0.4 else "warning" if kappa >= 0.2 else "critical"
            pct, vtext = max(0.0, kappa), f"kappa {kappa:.2f}"
        ci = ""
        if ag.get("kappa_ci95"):
            lo, hi = ag["kappa_ci95"]
            ci = f"CI {lo:.2f} to {hi:.2f}"
        meters.append(
            card_mod.Meter(f"Agreement with humans ({acc:.0%} acc)", pct, status, vtext, ci)
        )
        # agreement stays its own meter; the headline is the no-label coin-flip summary

    return meters, sentences


def judge_check_now(
    spec: str,
    *,
    logs: list[str] | None = None,
    prompt_file: str | None = None,
    pairs: int = 20,
    trials: int = 5,
    probe_trials: int = 3,
    yes: bool = False,
    base_url: str | None = None,
    temperature: float = 0.7,
    workspace: str | Path = "judgecheck",
    backend: Backend | None = None,
    make_card: bool = True,
    progress: Progress | None = None,
    fmt: str | None = None,
) -> dict[str, Any]:
    plan = build_plan(
        spec,
        logs=logs,
        prompt_file=prompt_file,
        pairs=pairs,
        trials=trials,
        probe_trials=probe_trials,
        base_url=base_url,
        temperature=temperature,
        workspace=workspace,
        backend=backend,
        fmt=fmt,
    )
    b: Backend = plan["backend"]
    ws: Workspace = plan["workspace"]
    requests = plan["requests"]
    n_calls = len(requests)
    plan_line = b.describe(n_calls)

    if b.paid and not yes:
        return {
            "ran": False,
            "needs_confirmation": True,
            "judge": b.id,
            "model": b.model,
            "calls": n_calls,
            "estimated_cost": round(b.cost_per_call * n_calls, 2) if b.cost_per_call else None,
            "plan": plan_line,
            "message": f"{plan_line}\nThis judge spends money. Re-run with --yes to proceed.",
        }
    if backend is None:
        problem = preflight(b)
        if problem:
            raise ValueError(f"cannot run {b.model!r}: {problem}")

    # A one-shot check should not leave a multi-GB model pinned in memory (some Ollama setups
    # keep models loaded forever), so unload it afterwards, but only if this run loaded it.
    was_loaded = ollama_loaded(b) if backend is None else None
    t0 = time.monotonic()
    try:
        rows, errors = _run_requests(b, requests, progress)
    finally:
        if was_loaded is False:
            ollama_unload(b)
    seconds = round(time.monotonic() - t0, 1)

    # persist the evidence
    write_jsonl(ws.judge_requests, requests)
    write_jsonl(ws.judgments, rows)
    if plan["labels"]:
        write_jsonl(ws.labels, [{"case_id": c, "label": v} for c, v in plan["labels"].items()])

    ncases, nlabels = len(plan["cases"]), len(plan["labels"])
    th = Thresholds(
        min_cases=min(10, ncases),
        min_labeled=min(20, nlabels) if nlabels else 20,
    )
    j = check_judge(rows, plan["labels"], th)

    meters, sentences = build_meters(j, plan["mode"])
    risk = _worst([m.status for m in meters])
    headline = capitalize_first("; ".join(sentences) + ".") if sentences else "No probe ran."
    invalid = j["stability"]["invalid_outputs"]

    card_paths: dict[str, str] = {}
    if make_card:
        card = card_mod.Card(
            model=b.model,
            risk=risk,
            headline=headline,
            meters=meters,
            n_text=f"n = {ncases} {'pairs' if plan['mode'] == 'pairwise' else 'cases'}, "
            f"{n_calls} calls",
            date=date.today().isoformat(),
            source=plan["source"].get("citation") or "your logs",
            reproduce=f"uvx eval-builder judge-check {spec}",
        )
        card_paths = card_mod.write_card(card, ws.root / "card.svg")

    result = {
        "ran": True,
        "judge": b.id,
        "model": b.model,
        "kind": b.kind,
        "mode": plan["mode"],
        "prompt_hash": plan["prompt_hash"],
        "coin_flip_risk": card_mod.RISK_WORD[risk],
        "verdict": j["verdict"],
        "headline": headline,
        "reasons": j["reasons"],
        "metrics": [asdict(m) for m in meters],
        "cases": ncases,
        "labeled_cases": nlabels,
        "calls": n_calls,
        "errors": errors,
        "invalid_outputs": invalid,
        "seconds": seconds,
        "source": plan["source"],
        "workspace": str(ws.root),
        "judgments_file": str(ws.judgments),
        "card": card_paths,
        "summary": j,
        "plan": plan_line,
    }
    saved = {k: v for k, v in result.items() if k != "summary"}
    write_json(ws.root / "judge_check_now.json", saved)
    return result


def capitalize_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def verdict_block(result: dict[str, Any]) -> str:
    """The one-screen text verdict for the CLI."""
    if result.get("needs_confirmation"):
        return result["message"]
    lines = [
        f"Coin flip risk: {result['coin_flip_risk']}   (judge-check verdict: {result['verdict']})",
        "",
        result["headline"],
        "",
    ]
    for m in result["metrics"]:
        ci = f"  {m['ci_text']}" if m["ci_text"] else ""
        lines.append(f"  {m['label']:<34} {m['value_text']:>10}{ci}")
    lines.append("")
    extra = []
    if result["errors"]:
        extra.append(f"{result['errors']} call(s) errored")
    if result["invalid_outputs"]:
        extra.append(f"{result['invalid_outputs']} unparseable judge output(s)")
    tail = f"{result['cases']} cases, {result['calls']} calls in {result['seconds']}s"
    if extra:
        tail += " (" + ", ".join(extra) + ")"
    lines.append(tail)
    if result.get("card"):
        for kind, path in result["card"].items():
            lines.append(f"card ({kind}): {path}")
    lines.append(f"details: {result['judgments_file']}")
    return "\n".join(lines)
