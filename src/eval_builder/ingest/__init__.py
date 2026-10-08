"""Read traces from supported formats, normalize, redact, and write traces.jsonl."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..io import sha256_file, write_json, write_jsonl
from ..redact import Redactor
from ..schema import Trace
from ..workspace import Workspace
from .formats import FORMATS, PARSERS, SkipRecord, detect_format, iter_otel_spans, parse_otel_trace

__all__ = ["FORMATS", "ingest", "load_records", "parse_file"]


def load_records(path: Path) -> list[Any]:
    """Load a .json file (array, object, or {"data": [...]}) or a .jsonl file."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, list):
            return doc
        if isinstance(doc, dict):
            if isinstance(doc.get("data"), list) and "resourceSpans" not in doc:
                return doc["data"]
            if isinstance(doc.get("traces"), list):
                return doc["traces"]
            return [doc]
    records = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{lineno}: not valid JSON or JSONL ({e.msg})") from e
    return records


def parse_file(path: Path, fmt: str | None = None) -> tuple[str, list[Trace], Counter[str], int]:
    """Return (format, traces, skip reasons, records read)."""
    records = load_records(path)
    fmt = fmt or detect_format(records)
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}")
    skipped: Counter[str] = Counter()
    traces: list[Trace] = []
    name = path.name
    if fmt == "otel":
        groups: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for rec in records:
            if not isinstance(rec, dict):
                skipped["not a JSON object"] += 1
                continue
            for span in iter_otel_spans(rec):
                tid = str(
                    span.get("traceId")
                    or span.get("trace_id")
                    or (span.get("context") or {}).get("trace_id")
                    or ""
                )
                if tid not in groups:
                    order.append(tid)
                groups.setdefault(tid, []).append(span)
        for i, tid in enumerate(order):
            try:
                traces.append(parse_otel_trace(tid, groups[tid], name, i))
            except SkipRecord as e:
                skipped[str(e)] += 1
        return fmt, traces, skipped, len(records)
    parser = PARSERS[fmt]
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            skipped["not a JSON object"] += 1
            continue
        try:
            t = parser(rec, name, i)
        except SkipRecord as e:
            skipped[str(e)] += 1
            continue
        except (TypeError, AttributeError, KeyError) as e:
            skipped[f"malformed record ({type(e).__name__})"] += 1
            continue
        if not t.input.strip() and not t.output.strip():
            skipped["empty input and output"] += 1
            continue
        if not t.input.strip():
            skipped["no user message"] += 1
            continue
        traces.append(t)
    return fmt, traces, skipped, len(records)


def _expand(paths: Sequence[str | Path]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted(x for x in p.rglob("*") if x.suffix in (".json", ".jsonl")))
        elif p.exists():
            out.append(p)
        else:
            raise FileNotFoundError(f"no such file or directory: {p}")
    return out


def _redact_trace(t: Trace, r: Redactor) -> Trace:
    r.start_trace(t.id)
    contents = {m["content"] for m in t.messages}
    t.messages = [{"role": m["role"], "content": r.text(m["content"])} for m in t.messages]
    # input and output are copies of message text; do not count their matches twice
    t.input = r.text(t.input, count=t.input not in contents)
    t.output = r.text(t.output, count=t.output not in contents)
    t.system = r.text(t.system) if t.system else t.system
    t.metadata = r.value(t.metadata)
    return t


def ingest(
    paths: Sequence[str | Path],
    workspace: str | Path,
    fmt: str | None = None,
    redact: bool = True,
) -> dict[str, Any]:
    """Ingest one or more files or directories into the workspace. Overwrites traces.jsonl."""
    ws = Workspace.at(workspace).ensure()
    redactor = Redactor(enabled=redact)
    all_traces: list[Trace] = []
    sources = []
    seen_ids: Counter[str] = Counter()
    for path in _expand(paths):
        used_fmt, traces, skipped, n_records = parse_file(path, fmt)
        for t in traces:
            seen_ids[t.id] += 1
            if seen_ids[t.id] > 1:
                t.id = f"{t.id}~{seen_ids[t.id]}"
            all_traces.append(_redact_trace(t, redactor))
        sources.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "format": used_fmt,
                "records": n_records,
                "traces": len(traces),
                "skipped": dict(skipped),
            }
        )
    write_jsonl(ws.traces, (t.to_dict() for t in all_traces))
    summary = {
        "traces": len(all_traces),
        "sources": sources,
        "redactions": redactor.summary(),
        "with_error": sum(t.error for t in all_traces),
        "feedback": dict(Counter(t.feedback or "none" for t in all_traces)),
        "routes": dict(Counter(t.route or "none" for t in all_traces).most_common(20)),
        "tools": dict(Counter(tool for t in all_traces for tool in t.tools).most_common(20)),
        "multi_turn": sum(
            1 for t in all_traces if sum(m["role"] == "user" for m in t.messages) > 1
        ),
        "output_file": str(ws.traces),
    }
    write_json(ws.ingest_report, summary)
    return summary


def load_traces(workspace: str | Path) -> list[Trace]:
    from ..io import read_jsonl

    ws = Workspace.at(workspace)
    if not ws.traces.exists():
        raise FileNotFoundError(f"{ws.traces} not found; run `eval-builder ingest` first")
    return [Trace.from_dict(d) for d in read_jsonl(ws.traces)]
