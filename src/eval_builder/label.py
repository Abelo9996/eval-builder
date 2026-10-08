"""Human labels: pick the cases a person should label, write an offline sheet to label
them in (HTML, plus CSV for spreadsheet users), and import what comes back.

eval-builder never labels anything. It decides which cases are worth a person's time,
and it keeps the bookkeeping exact: the sheet exports labels.jsonl rows in the format
judge-check reads, and `label import` checks every row against cases.yaml before it
merges it into the workspace.

Which cases: split the budget evenly across outcomes (the judges' consensus verdict, or
the logged failure flag before any judge has run) so a judge that always says "fail"
cannot look good; inside each outcome, give up to half the budget to the cases where
judges disagree, flip across repeats or move under padding (a label there tells the
judges apart), and spread the rest across topic clusters in a seeded random order.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .balance import skew_warning
from .draft import load_cases, load_rubric
from .io import read_jsonl, write_json, write_jsonl
from .judge.check import Thresholds, _load_judgments, check_judge, load_labels, normalize_label
from .judge.stats import majority
from .workspace import Workspace

DEFAULT_N = 24
DEFAULT_UNCERTAIN_SHARE = 0.5
POINTWISE_DEFAULT = ["pass", "fail"]
PAIRWISE_DEFAULT = ["A", "B"]
CSV_CELL_LIMIT = 32000  # spreadsheet apps cut cells at 32,767 characters
CSV_COLUMNS = (
    "case_id",
    "label",
    "note",
    "labeler",
    "allowed_labels",
    "mode",
    "expected_behavior",
    "criteria",
    "earlier_turns",
    "input",
    "reply",
    "answer_b",
)


def case_modes(
    cases: list[dict[str, Any]], rubric: dict[str, Any]
) -> dict[str, tuple[str, list[str]]]:
    """Mode and allowed labels per case: pairwise when the case has compare_output and the
    rubric has a pairwise judge, else pointwise. Labels come from the rubric's judges."""
    judges = rubric.get("judges") or []
    point = [j for j in judges if j.get("mode", "pointwise") == "pointwise"]
    pair = [j for j in judges if j.get("mode") == "pairwise"]

    def union(js: list[dict[str, Any]], default: list[str]) -> list[str]:
        out: list[str] = []
        for j in js:
            for lab in j.get("labels") or []:
                if str(lab) not in out and "TODO" not in str(lab):
                    out.append(str(lab))
        return out or list(default)

    point_labels = union(point, POINTWISE_DEFAULT)
    pair_labels = union(pair, PAIRWISE_DEFAULT)
    return {
        str(c["id"]): ("pairwise", pair_labels)
        if pair and c.get("compare_output")
        else ("pointwise", point_labels)
        for c in cases
    }


def _cluster(case: dict[str, Any]) -> str:
    for t in case.get("tags") or []:
        if str(t).startswith("cluster:"):
            return str(t)
    return "cluster:?"


def _judge_details(ws: Workspace) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    """Per case, per judge: the per-case detail judge-check computes (majority, flips)."""
    if not ws.judgments.exists():
        return {}, []
    rows = _load_judgments(ws.judgments, ws.judge_requests)
    by_judge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_judge[str(r["judge"])].append(r)
    per_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for jid, jrows in by_judge.items():
        for c in check_judge(jrows, {}, Thresholds(min_trials=1))["cases"]:
            per_case[str(c["case_id"])][jid] = c
    return per_case, sorted(by_judge)


def _signal(details: dict[str, dict[str, Any]]) -> dict[str, Any]:
    majorities = {j: d["majority"] for j, d in sorted(details.items())}
    flipped = {j: d["counts"] for j, d in sorted(details.items()) if d["flipped"]}
    pad_moved = [
        j
        for j, d in sorted(details.items())
        if "pad_majority" in d and d["pad_majority"] != d["majority"]
    ]
    said = [m for m in majorities.values() if m is not None]
    consensus, _ = majority(said)
    disagree = len(set(said)) > 1
    n = max(1, len(details))
    score = (2.0 if disagree else 0.0) + len(flipped) / n + 0.5 * len(pad_moved) / n
    reasons = []
    if disagree:
        reasons.append(
            "judges disagree: "
            + ", ".join(f"{j} says {m or 'no majority'}" for j, m in majorities.items())
        )
    for j, counts in flipped.items():
        spread = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        reasons.append(f"{j} changed its verdict across repeats ({spread})")
    for j in pad_moved:
        reasons.append(f"irrelevant padding changed {j}'s verdict")
    return {
        "judge_majorities": majorities,
        "consensus": consensus,
        "disagree": disagree,
        "flipped": sorted(flipped),
        "pad_moved": pad_moved,
        "uncertainty": round(score, 4),
        "reasons": reasons,
    }


def _allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Split n evenly across strata; what a small stratum cannot use goes to the others."""
    quota = dict.fromkeys(sizes, 0)
    left = n
    active = sorted(s for s, k in sizes.items() if k > 0)
    while left > 0 and active:
        share = max(1, left // len(active))
        for s in active:
            take = min(share, sizes[s] - quota[s], left)
            quota[s] += take
            left -= take
        active = [s for s in active if quota[s] < sizes[s]]
    return quota


def _spread(cands: list[dict[str, Any]], k: int, rng: random.Random) -> list[dict[str, Any]]:
    """k cases taken round-robin across topic clusters, in a seeded random order."""
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cands:
        by_cluster[_cluster(c)].append(c)
    order = sorted(by_cluster)
    rng.shuffle(order)
    for cl in order:
        rng.shuffle(by_cluster[cl])
    out: list[dict[str, Any]] = []
    while len(out) < k and any(by_cluster[cl] for cl in order):
        for cl in order:
            if by_cluster[cl] and len(out) < k:
                out.append(by_cluster[cl].pop(0))
    return out


def _labeled_ids(ws: Workspace) -> set[str]:
    if not ws.labels.exists():
        return set()
    return {str(r.get("case_id")) for r in read_jsonl(ws.labels) if r.get("label") is not None}


def pick_cases(
    cases: list[dict[str, Any]],
    signals: dict[str, dict[str, Any]],
    n: int = DEFAULT_N,
    seed: int = 0,
    uncertain_share: float = DEFAULT_UNCERTAIN_SHARE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pick up to n cases. Returns (picks with reasons, strata report)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if not 0.0 <= uncertain_share <= 1.0:
        raise ValueError("uncertain_share must be between 0 and 1")
    rng = random.Random(seed)

    def stratum(c: dict[str, Any]) -> str:
        sig = signals.get(str(c["id"]))
        if sig:
            return f"judges say {sig['consensus']}" if sig["consensus"] else "judges split"
        return "logged failure" if c.get("observed_failure") else "no failure logged"

    members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        members[stratum(c)].append(c)
    quota = _allocate({s: len(v) for s, v in members.items()}, n)
    picks: list[dict[str, Any]] = []
    for s in sorted(members):
        q = quota[s]
        if not q:
            continue
        pool = members[s]
        unc = sorted(
            (c for c in pool if signals.get(str(c["id"]), {}).get("uncertainty", 0) > 0),
            key=lambda c: (-signals[str(c["id"])]["uncertainty"], str(c["id"])),
        )
        chosen = unc[: min(len(unc), math.ceil(q * uncertain_share))]
        taken = {str(c["id"]) for c in chosen}
        rest = _spread([c for c in pool if str(c["id"]) not in taken], q - len(chosen), rng)
        for c in chosen + rest:
            sig = signals.get(str(c["id"]))
            reasons = [f"outcome stratum '{s}' ({len(pool)} candidates, {q} picked)"]
            if str(c["id"]) in taken and sig:
                reasons += sig["reasons"]
            else:
                reasons.append(f"spread across topics ({_cluster(c)})")
            picks.append({"case_id": str(c["id"]), "stratum": s, "reasons": reasons})
    rng.shuffle(picks)  # mixed order, so strata and hard cases do not come in blocks
    strata = {s: {"candidates": len(v), "picked": quota[s]} for s, v in sorted(members.items())}
    return picks, strata


def _context_turns(case: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
        for m in case.get("context") or []
    ]


def _criteria(case: dict[str, Any], rubric: dict[str, Any]) -> list[dict[str, str]]:
    desc = {str(c.get("id")): str(c.get("description", "")) for c in rubric.get("criteria") or []}
    return [{"id": str(k), "description": desc.get(str(k), "")} for k in case.get("criteria") or []]


def label(
    workspace: str | Path,
    n: int = DEFAULT_N,
    seed: int = 0,
    include_labeled: bool = False,
    uncertain_share: float = DEFAULT_UNCERTAIN_SHARE,
) -> dict[str, Any]:
    """Pick cases for a person to label and write label_sheet.html and label_sheet.csv."""
    from .label_sheet import render_sheet

    ws = Workspace.at(workspace)
    doc = load_cases(ws.root)
    rubric = load_rubric(ws.root) if ws.rubric.exists() else {}
    ready = [c for c in doc.get("cases") or [] if c.get("status") == "ready"]
    if not ready:
        raise ValueError(
            "no cases have status: ready; judges only run on ready cases, so labels on other "
            "cases are never used. Fill expected_behavior and set status: ready (update_case), "
            "then run label again"
        )
    modes = case_modes(ready, rubric)
    done = _labeled_ids(ws)
    cands = ready if include_labeled else [c for c in ready if str(c["id"]) not in done]
    if not cands:
        raise ValueError(
            f"all {len(ready)} ready cases already have labels in {ws.labels.name}; pass "
            "include_labeled (CLI --include-labeled) to have them labeled again, for example "
            "by a second person"
        )
    details, judges = _judge_details(ws)
    signals = {cid: _signal(d) for cid, d in details.items()}
    picks, strata = pick_cases(cands, signals, n, seed, uncertain_share)
    by_id = {str(c["id"]): c for c in cands}
    created = datetime.now(UTC).isoformat(timespec="seconds")
    sheet_id = hashlib.sha256(
        json.dumps([str(ws.root.resolve()), [p["case_id"] for p in picks], created]).encode()
    ).hexdigest()[:12]
    sheet_cases = []
    for p in picks:
        c = by_id[p["case_id"]]
        mode, allowed = modes[p["case_id"]]
        sheet_cases.append(
            {
                "id": p["case_id"],
                "mode": mode,
                "labels": allowed,
                "context": _context_turns(c),
                "input": str(c.get("input") or ""),
                "output": str(c.get("observed_output") or ""),
                "compare_output": str(c.get("compare_output") or ""),
                "expected_behavior": str(c.get("expected_behavior") or ""),
                "criteria": _criteria(c, rubric),
            }
        )
    sheet = {
        "format": "eval-builder-label-sheet",
        "version": 1,
        "sheet_id": sheet_id,
        "created": created,
        "suite": str(doc.get("suite") or ""),
        "workspace": str(ws.root.resolve()),
        "cases": sheet_cases,
    }
    ws.label_sheet_html.write_text(render_sheet(sheet), encoding="utf-8")
    _write_csv(ws.label_sheet_csv, sheet_cases)
    uncertain = sum(1 for p in picks if signals.get(p["case_id"], {}).get("uncertainty", 0) > 0)
    notes = []
    if len(picks) < n:
        notes.append(
            f"asked for {n} but only {len(cands)} ready case(s) need a label, so all were picked"
        )
    if done and not include_labeled:
        notes.append(
            f"{len(done & {str(c['id']) for c in ready})} ready case(s) already labeled, skipped"
        )
    if not judges:
        notes.append(
            "no judgments yet, so outcomes come from the logged failure flag; after the judges "
            "have run, run label again to aim the next labels at cases where judges disagree"
        )
    elif uncertain:
        notes.append(
            f"{uncertain} of {len(picks)} picks are cases where judges disagree, flip or move "
            "under padding. They tell judges apart, but they are harder than a random case, so "
            "agreement measured on them is on the pessimistic side"
        )
    plan = {
        "sheet_id": sheet_id,
        "created": created,
        "label_sheet_html": str(ws.label_sheet_html),
        "label_sheet_csv": str(ws.label_sheet_csv),
        "params": {
            "n": n,
            "seed": seed,
            "include_labeled": include_labeled,
            "uncertain_share": uncertain_share,
        },
        "ready_cases": len(ready),
        "already_labeled": len(done),
        "candidates": len(cands),
        "judges": judges,
        "strata": strata,
        "picked": len(picks),
        "uncertain_picked": uncertain,
        "picks": [{**p, "signal": signals.get(p["case_id"])} for p in picks],
        "notes": notes,
    }
    write_json(ws.label_plan, plan)
    return {
        **{k: v for k, v in plan.items() if k != "picks"},
        "plan_file": str(ws.label_plan),
        "picks": [{"case_id": p["case_id"], "reasons": p["reasons"]} for p in picks],
        "next": (
            f"ask a person to open {ws.label_sheet_html} in a browser (it works offline), "
            "label every case, click Export and save labels.jsonl, then run `eval-builder "
            f"label import <that file> -w {ws.root}` (MCP: label_import). Spreadsheet users "
            f"can fill the label column of {ws.label_sheet_csv.name} and import that instead. "
            "Do not fill in the sheet yourself: the labels are what the judges are checked "
            "against"
        ),
    }


def _cell(v: str) -> str:
    if len(v) <= CSV_CELL_LIMIT:
        return v
    return v[:CSV_CELL_LIMIT] + " [cut here; the full text is in label_sheet.html]"


def _write_csv(path: Path, sheet_cases: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for c in sheet_cases:
            turns = "\n\n".join(f"{t['role']}: {t['content']}" for t in c["context"])
            w.writerow(
                {
                    "case_id": c["id"],
                    "label": "",
                    "note": "",
                    "labeler": "",
                    "allowed_labels": " / ".join(c["labels"]),
                    "mode": c["mode"],
                    "expected_behavior": _cell(c["expected_behavior"]),
                    "criteria": "\n".join(f"{k['id']}: {k['description']}" for k in c["criteria"]),
                    "earlier_turns": _cell(turns),
                    "input": _cell(c["input"]),
                    "reply": _cell(c["output"]),
                    "answer_b": _cell(c["compare_output"]),
                }
            )


def _parse_rows(text: str, csv_like: bool) -> list[dict[str, Any]]:
    text = text.lstrip("﻿")
    if csv_like:
        return list(csv.DictReader(io.StringIO(text)))
    stripped = text.strip()
    if not stripped:
        return []
    try:
        whole = json.loads(stripped)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, list):
        return [r for r in whole if isinstance(r, dict)]
    if isinstance(whole, dict):
        rows = whole.get("labels")
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else [whole]
    out = []
    for i, line in enumerate(stripped.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"line {i} is not JSON ({e.msg}); import takes the labels.jsonl the sheet "
                "exports, a JSON list of {case_id, label} rows, or the filled-in CSV"
            ) from e
        if isinstance(row, dict):
            out.append(row)
    return out


def label_import(
    workspace: str | Path, path: str | Path, labeler: str | None = None
) -> dict[str, Any]:
    """Check labels from the sheet (or CSV, or pasted JSON) and merge them into labels.jsonl.

    A new label replaces an earlier one for the same case from the same labeler; labels
    from other labelers are kept (judge-check resolves several per case by majority).
    """
    ws = Workspace.at(workspace)
    src = str(path)
    if src == "-":
        text, csv_like = sys.stdin.read(), False
        if text.lstrip("﻿").startswith("case_id,"):
            csv_like = True
    else:
        p = Path(src).expanduser()
        if not p.exists():
            raise FileNotFoundError(
                f"{p} not found; give the file the label sheet exported (labels.jsonl, often "
                "in your Downloads folder) or the filled-in label_sheet.csv"
            )
        text = p.read_text(encoding="utf-8-sig")
        csv_like = p.suffix.lower() == ".csv"
    rows = _parse_rows(text, csv_like)
    doc = load_cases(ws.root)
    cases = {str(c.get("id")): c for c in doc.get("cases") or []}
    rubric = load_rubric(ws.root) if ws.rubric.exists() else {}
    modes = case_modes(list(cases.values()), rubric)
    imported: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []
    skipped_blank = 0
    not_ready: set[str] = set()
    for i, r in enumerate(rows, 1):
        cid = str(r.get("case_id") or "").strip()
        raw = r.get("label")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            skipped_blank += 1
            continue
        if cid not in modes:
            rejected.append(
                {"row": str(i), "case_id": cid, "problem": "no such case in cases.yaml"}
            )
            continue
        mode, allowed = modes[cid]
        canon = {normalize_label(a, mode): a for a in allowed}
        lab = normalize_label(raw.strip() if isinstance(raw, str) else raw, mode)
        if lab not in canon:
            rejected.append(
                {
                    "row": str(i),
                    "case_id": cid,
                    "problem": f"label {raw!r} is not one of {allowed}",
                }
            )
            continue
        who = str(r.get("labeler") or labeler or "").strip()
        row: dict[str, Any] = {"case_id": cid, "label": lab, "mode": mode}
        if who:
            row["labeler"] = who
        note = str(r.get("note") or "").strip()
        if note:
            row["note"] = note
        for k in ("labeled_at", "sheet"):
            if r.get(k):
                row[k] = str(r[k])
        row["source"] = Path(src).name if src != "-" else "stdin"
        imported[(cid, who)] = row
        if cases[cid].get("status") != "ready":
            not_ready.add(cid)
    existing = list(read_jsonl(ws.labels)) if ws.labels.exists() else []
    kept = [
        r
        for r in existing
        if (str(r.get("case_id")), str(r.get("labeler") or "").strip()) not in imported
    ]
    replaced = len(existing) - len(kept)
    if imported:
        write_jsonl(ws.labels, kept + list(imported.values()))
    resolved = (
        load_labels(ws.labels, {k: m for k, (m, _) in modes.items()}) if ws.labels.exists() else {}
    )
    counts = dict(Counter(resolved.values()))
    warnings = []
    if not_ready:
        warnings.append(
            f"{len(not_ready)} labeled case(s) are not ready ({', '.join(sorted(not_ready)[:5])}"
            f"{', ...' if len(not_ready) > 5 else ''}); judges only run on ready cases"
        )
    skew = skew_warning(
        counts,
        "human labels",
        "Label more cases of the other outcome; `eval-builder label` picks across outcomes",
    )
    if skew:
        warnings.append(skew)
    min_labeled = Thresholds().min_labeled
    if rejected:
        nxt = (
            "fix the rejected rows (case ids must exist in cases.yaml, labels must be one of "
            "the allowed labels) and import again; importing again replaces your earlier labels"
        )
    elif len(resolved) < min_labeled:
        nxt = (
            f"{len(resolved)} case(s) have a label; judge-check needs at least {min_labeled} "
            "to call a judge trustworthy. Run `eval-builder label` for another sheet, or run "
            "judge-check now for what these labels already show"
        )
    else:
        nxt = "run judge-check (MCP: judge_check) to compare each judge with these labels"
    return {
        "labels_file": str(ws.labels),
        "rows_read": len(rows),
        "imported": len(imported),
        "replaced": replaced,
        "skipped_blank": skipped_blank,
        "rejected": rejected[:50],
        "rejected_count": len(rejected),
        "labeled_cases": len(resolved),
        "label_counts": counts,
        "warnings": warnings,
        "next": nxt,
    }
