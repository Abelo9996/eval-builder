"""Measure how far each judge can be trusted.

For every judge: self-consistency over repeated trials (flip rate), agreement with
human labels (accuracy with a Wilson interval, Cohen's kappa with an approximate
interval), a position probe (swap answer order) and a verbosity probe (pad with
irrelevant text). A verdict is derived from explicit, configurable thresholds and
every verdict lists the numbers behind it.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..balance import proportions, skew_warning
from ..io import read_jsonl, write_json
from ..workspace import Workspace
from .stats import cohen_kappa, kappa_interval, majority, majority_vote_stability, wilson

NO_MAJORITY = "(no majority)"
POSITIVE = {"pass", "yes", "true", "good", "correct", "acceptable", "1"}
VERDICTS = ("trustworthy", "unstable", "biased", "misaligned", "not_enough_data")


@dataclass
class Thresholds:
    min_trials: int = 3
    min_cases: int = 10
    max_flip_rate: float = 0.2
    min_position_consistency: float = 0.8
    max_toward_padded_rate: float = 0.1
    min_kappa: float = 0.4
    min_labeled: int = 20


_FENCE = re.compile(r"^```(?:json)?|```$", re.I | re.M)
_JSON_FIELD = re.compile(r'"(verdict|label|pass|winner)"\s*:\s*"?([A-Za-z0-9_]+)', re.I)
_PAIR_A = re.compile(r"^\W*(?:\[\[)?\s*(?:answer\s*|assistant\s*|response\s*)?a\b", re.I)
_PAIR_B = re.compile(r"^\W*(?:\[\[)?\s*(?:answer\s*|assistant\s*|response\s*)?b\b", re.I)
_PAIR_TIE = re.compile(r"^\W*(?:\[\[)?\s*(?:tie|c|equal|draw|both)\b", re.I)


def normalize_verdict(v: Any, mode: str) -> str:
    """Canonical label for a judge's raw output. Unparseable pairwise outputs become 'invalid'."""
    if v is None:
        return "invalid"
    if isinstance(v, str):
        text = _FENCE.sub("", v.strip()).strip()
        if text.startswith("{"):
            # a judge that answers in JSON, for example promptfoo's {"pass": ..., "reason": ...}
            try:
                v = json.loads(text)
            except json.JSONDecodeError:
                # cut off mid-reason (token limit): the verdict field usually came first
                m = _JSON_FIELD.search(text)
                if not m:
                    return "invalid"
                val = m.group(2)
                v = {"true": True, "false": False}.get(val.lower(), val)
    if isinstance(v, dict):
        for key in ("verdict", "label", "pass", "winner"):
            if key in v:
                return normalize_verdict(v[key], mode)
        return "invalid"
    if isinstance(v, bool):
        return "pass" if v else "fail"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    s = str(v).strip()
    if mode == "pairwise":
        if _PAIR_TIE.match(s):
            return "tie"
        if _PAIR_A.match(s):
            return "A"
        if _PAIR_B.match(s):
            return "B"
        if s in ("1", "first"):
            return "A"
        if s in ("2", "second"):
            return "B"
        return "invalid"
    s = s.lower().strip(" .!\"'")
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return s or "invalid"


def normalize_label(v: Any, mode: str) -> str:
    if mode == "pairwise" and isinstance(v, str) and v.lower() in ("model_a", "a"):
        return "A"
    if mode == "pairwise" and isinstance(v, str) and v.lower() in ("model_b", "b"):
        return "B"
    return normalize_verdict(v, mode)


def unswap(label: str) -> str:
    return {"A": "B", "B": "A"}.get(label, label)


def _favorable(label: str | None, other: str | None, mode: str, pad_side: str | None) -> bool:
    """Did the verdict move toward the padded answer?"""
    if label is None:
        return False
    if mode == "pairwise":
        return label == pad_side and other != pad_side
    try:
        return other is not None and float(label) > float(other)
    except ValueError:
        return label in POSITIVE and (other not in POSITIVE)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _rate(k: int, n: int) -> dict[str, Any]:
    ci = wilson(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
    }


def _load_judgments(path: Path, requests_path: Path | None) -> list[dict[str, Any]]:
    req_index: dict[str, dict[str, Any]] = {}
    if requests_path and requests_path.exists():
        req_index = {r["request_id"]: r for r in read_jsonl(requests_path)}
    rows = []
    for r in read_jsonl(path):
        if "case_id" not in r and r.get("request_id") in req_index:
            base = {
                k: v
                for k, v in req_index[r["request_id"]].items()
                if k not in ("presented", "prompt")
            }
            r = {**base, **r}
        if "judge" not in r or "case_id" not in r:
            raise ValueError(
                f"judgment row has no judge/case_id and its request_id "
                f"{r.get('request_id')!r} is not in judge_requests.jsonl; write rows as "
                '{"request_id": "<id from judge_requests.jsonl>", "verdict": "<label>"}'
            )
        rows.append(r)
    return rows


def load_labels(path: Path, mode_by_case: dict[str, str] | None = None) -> dict[str, str]:
    """Human labels per case. Several rows for one case are resolved by strict majority."""
    raw: dict[str, list[str]] = defaultdict(list)
    for r in read_jsonl(path):
        cid = str(r["case_id"])
        mode = r.get("mode") or (mode_by_case or {}).get(cid, "pointwise")
        raw[cid].append(normalize_label(r.get("label"), mode))
    out = {}
    for cid, labels in raw.items():
        lab, _ = majority(labels)
        if lab is not None:
            out[cid] = lab
    return out


def check_judge(
    rows: list[dict[str, Any]], labels: dict[str, str], th: Thresholds
) -> dict[str, Any]:
    mode = rows[0].get("mode", "pointwise")
    by_probe: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    raw_presented: list[str] = []
    pad_side: dict[str, str | None] = {}
    invalid = 0
    for r in rows:
        label = normalize_verdict(r.get("verdict"), mode)
        if label == "invalid":
            invalid += 1
        probe = r.get("probe") or "none"
        if mode == "pairwise" and probe in ("none", "swap") and label in ("A", "B"):
            raw_presented.append(label)
        if probe == "swap":
            label = unswap(label)
        by_probe[probe][str(r["case_id"])].append(label)
        if probe == "pad":
            pad_side[str(r["case_id"])] = r.get("pad_side")

    base = by_probe.get("none", {})
    per_case: dict[str, dict[str, Any]] = {}
    for cid, labs in base.items():
        maj, share = majority(labs)
        per_case[cid] = {
            "case_id": cid,
            "trials": len(labs),
            "counts": dict(Counter(labs)),
            "majority": maj,
            "majority_share": round(share, 4),
            "flipped": len(set(labs)) > 1,
            "majority_of_3_stability": majority_vote_stability(Counter(labs), 3),
        }
    eligible = [c for c in per_case.values() if c["trials"] >= th.min_trials]
    flipped = sum(1 for c in eligible if c["flipped"])
    stability = {
        "cases": len(eligible),
        "trials_per_case": sorted({c["trials"] for c in per_case.values()}),
        "flip_rate": _rate(flipped, len(eligible)),
        "mean_self_agreement": round(sum(c["majority_share"] for c in eligible) / len(eligible), 4)
        if eligible
        else None,
        "no_majority_cases": sum(1 for c in eligible if c["majority"] is None),
        "majority_of_3_stability": _mean(
            [
                c["majority_of_3_stability"]
                for c in eligible
                if c["majority_of_3_stability"] is not None
            ]
        ),
        "invalid_outputs": invalid,
        "calls": len(rows),
    }

    # agreement with human labels, using each case's majority verdict
    agreement: dict[str, Any] | None = None
    labeled = [c for c in eligible if c["case_id"] in labels]
    if labeled:
        judge_labels = [c["majority"] or NO_MAJORITY for c in labeled]
        human = [labels[c["case_id"]] for c in labeled]
        for c in labeled:
            c["human"] = labels[c["case_id"]]
        correct = sum(j == h for j, h in zip(judge_labels, human, strict=True))
        kappa, po, pe = cohen_kappa(judge_labels, human)
        kci = kappa_interval(po, pe, len(labeled))
        single = [(lab, labels[cid]) for cid, labs in base.items() if cid in labels for lab in labs]
        agreement = {
            "cases": len(labeled),
            "accuracy": _rate(correct, len(labeled)),
            "kappa": round(kappa, 4) if kappa is not None else None,
            "kappa_ci95": [round(kci[0], 4), round(kci[1], 4)] if kci else None,
            "chance_agreement": round(pe, 4),
            "single_call_accuracy": round(sum(a == b for a, b in single) / len(single), 4)
            if single
            else None,
            "human_label_counts": dict(Counter(human)),
            "judge_label_counts": dict(Counter(judge_labels)),
            # accuracy of a judge that always gives the most common human label
            "majority_baseline": round(Counter(human).most_common(1)[0][1] / len(human), 4),
        }

    # position probe: majority in swapped order vs original order
    position: dict[str, Any] | None = None
    if mode == "pairwise" and by_probe.get("swap"):
        pairs = []
        for cid, labs in by_probe["swap"].items():
            smaj, _ = majority(labs)
            if cid in per_case:
                per_case[cid]["swap_majority"] = smaj
                pairs.append((per_case[cid]["majority"], smaj))
        consistent = sum(1 for a, b in pairs if a is not None and a == b)
        first = sum(1 for x in raw_presented if x == "A")
        position = {
            "cases": len(pairs),
            "consistency": _rate(consistent, len(pairs)),
            "first_position_rate": _rate(first, len(raw_presented)),
            "note": "consistency = share of cases whose majority verdict survives swapping the "
            "answer order; first_position_rate = share of A/B verdicts naming whichever "
            "answer was shown first (0.5 means no position preference)",
        }

    # verbosity probe: majority with irrelevant padding vs original
    verbosity: dict[str, Any] | None = None
    if by_probe.get("pad"):
        moved = toward = 0
        n = 0
        for cid, labs in by_probe["pad"].items():
            pmaj, _ = majority(labs)
            if cid not in per_case:
                continue
            n += 1
            orig = per_case[cid]["majority"]
            per_case[cid]["pad_majority"] = pmaj
            if pmaj != orig:
                moved += 1
                if _favorable(pmaj, orig, mode, pad_side.get(cid)):
                    toward += 1
        verbosity = {
            "cases": n,
            "changed": _rate(moved, n),
            "toward_padded": _rate(toward, n),
            "note": "padding appends an irrelevant paragraph; toward_padded = share of cases "
            "where the padded answer's verdict improved",
        }

    verdict, reasons, checks = _verdict(stability, agreement, position, verbosity, th)
    return {
        "mode": mode,
        "verdict": verdict,
        "reasons": reasons,
        "checks": checks,
        "stability": stability,
        "human_agreement": agreement,
        "position_probe": position,
        "verbosity_probe": verbosity,
        "cases": sorted(per_case.values(), key=lambda c: c["case_id"]),
    }


def _verdict(
    stability: dict[str, Any],
    agreement: dict[str, Any] | None,
    position: dict[str, Any] | None,
    verbosity: dict[str, Any] | None,
    th: Thresholds,
) -> tuple[str, list[str], dict[str, str]]:
    reasons: list[str] = []
    checks: dict[str, str] = {}
    if stability["cases"] < th.min_cases:
        checks["stability"] = "not enough data"
        reasons.append(
            f"only {stability['cases']} case(s) with >= {th.min_trials} trials "
            f"(need {th.min_cases})"
        )
        return "not_enough_data", reasons, checks
    fr = stability["flip_rate"]["rate"]
    unstable = fr > th.max_flip_rate
    checks["stability"] = "fail" if unstable else "pass"
    if unstable:
        reasons.append(
            f"verdict changed across repeated trials on {fr:.0%} of cases "
            f"(limit {th.max_flip_rate:.0%})"
        )
    biased = False
    if position and position["cases"] >= th.min_cases:
        pc = position["consistency"]["rate"]
        if pc < th.min_position_consistency:
            biased = True
            checks["position"] = "fail"
            reasons.append(
                f"verdict survived swapping answer order on only {pc:.0%} of cases "
                f"(need {th.min_position_consistency:.0%}); first-shown answer "
                f"picked {position['first_position_rate']['rate']:.0%} of the time"
            )
        else:
            checks["position"] = "pass"
    else:
        checks["position"] = "not run" if not position else "not enough data"
    if verbosity and verbosity["cases"] >= th.min_cases:
        tp = verbosity["toward_padded"]["rate"]
        if tp > th.max_toward_padded_rate:
            biased = True
            checks["verbosity"] = "fail"
            reasons.append(
                f"irrelevant padding moved the verdict toward the padded answer on "
                f"{tp:.0%} of cases (limit {th.max_toward_padded_rate:.0%})"
            )
        else:
            checks["verbosity"] = "pass"
    else:
        checks["verbosity"] = "not run" if not verbosity else "not enough data"
    misaligned = False
    if agreement and agreement["cases"] >= th.min_labeled:
        k = agreement["kappa"]
        if k is None or k < th.min_kappa:
            misaligned = True
            checks["human_agreement"] = "fail"
            reasons.append(
                f"agreement with human labels is low: kappa "
                f"{'undefined' if k is None else f'{k:.2f}'} (need {th.min_kappa}), "
                f"accuracy {agreement['accuracy']['rate']:.0%}"
            )
        else:
            checks["human_agreement"] = "pass"
    else:
        checks["human_agreement"] = "not enough data"
    if unstable:
        return "unstable", reasons, checks
    if biased:
        return "biased", reasons, checks
    if misaligned:
        return "misaligned", reasons, checks
    if checks["human_agreement"] != "pass":
        have = agreement["cases"] if agreement else 0
        reasons.append(
            f"stable, but only {have} case(s) have human labels (need "
            f"{th.min_labeled}); cannot tell whether it measures the right thing"
        )
        return "not_enough_data", reasons, checks
    k = agreement["kappa"] if agreement else None
    reasons.append(
        f"stable (flip rate {fr:.0%}), kappa {k:.2f} with humans"
        + (
            ""
            if checks["position"] == "pass" or checks["verbosity"] == "pass"
            else "; bias probes not run"
        )
    )
    return "trustworthy", reasons, checks


def judge_check(
    workspace: str | Path,
    judgments: str | Path | None = None,
    labels: str | Path | None = None,
    thresholds: Thresholds | None = None,
) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    th = thresholds or Thresholds()
    jpath = Path(judgments) if judgments else ws.judgments
    if not jpath.exists():
        hint = (
            "run judge_plan first, then run every request in judge_requests.jsonl"
            if not ws.judge_requests.exists()
            else "run every request in judge_requests.jsonl"
        )
        raise FileNotFoundError(
            f"{jpath} not found; {hint} and append {{request_id, verdict}} lines to it "
            "(or use `eval-builder judge-run --enable-judge-plugin --command "
            '"<judge>=<your command>"`)'
        )
    rows = _load_judgments(jpath, ws.judge_requests)
    by_judge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_judge[str(r["judge"])].append(r)
    mode_by_case = {str(r["case_id"]): r.get("mode", "pointwise") for r in rows}
    lpath = Path(labels) if labels else ws.labels
    human = load_labels(lpath, mode_by_case) if lpath.exists() else {}
    judges = {jid: check_judge(jrows, human, th) for jid, jrows in sorted(by_judge.items())}
    judged = {str(r["case_id"]) for r in rows}
    used = {cid: lab for cid, lab in human.items() if cid in judged}
    result = {
        "judge_check_file": str(ws.judge_check),
        "judgments_file": str(jpath),
        "labels_file": str(lpath) if lpath.exists() else None,
        "labeled_cases": len(human),
        "human_label_counts": dict(Counter(used.values())),
        "warnings": _balance_warnings(used, judges),
        "thresholds": asdict(th),
        "summary": [_summary(jid, r) for jid, r in judges.items()],
        "judges": judges,
        "trustworthy": [j for j, r in judges.items() if r["verdict"] == "trustworthy"],
    }
    result["next"] = _next_step(result, th, ws)
    write_json(ws.judge_check, result)
    return result


def _balance_warnings(used: dict[str, str], judges: dict[str, dict[str, Any]]) -> list[str]:
    """Warn when the labels (or a judge's answers on them) are mostly one outcome."""
    out = []
    w = skew_warning(
        Counter(used.values()),
        "the human labels on judged cases",
        "Have a person label more cases of the other outcome (`eval-builder label` picks "
        "across outcomes and aims at cases where judges disagree)",
    )
    if w:
        out.append(w)
    for jid, r in judges.items():
        ag = r["human_agreement"]
        if not ag or ag["cases"] < 5:
            continue
        jc = {k: v for k, v in ag["judge_label_counts"].items() if v}
        if len(jc) == 1:
            ((top, n),) = jc.items()
            out.append(
                f"judge {jid} gave the same verdict, {top!r}, on all {n} labeled cases; its "
                f"accuracy ({ag['accuracy']['rate']:.0%}) is just the share of {top!r} labels "
                f"({proportions(ag['human_label_counts'])})"
            )
    return out


def _summary(jid: str, r: dict[str, Any]) -> dict[str, Any]:
    """One row per judge with the point estimates, their 95% intervals and sample sizes."""
    agree = r["human_agreement"] or {}
    pos = r["position_probe"] or {}
    pad = r["verbosity_probe"] or {}

    def ci(d: dict[str, Any] | None) -> list[float] | None:
        return (d or {}).get("ci95")

    return {
        "judge": jid,
        "mode": r["mode"],
        "verdict": r["verdict"],
        "cases": r["stability"]["cases"],
        "calls": r["stability"]["calls"],
        "invalid_outputs": r["stability"]["invalid_outputs"],
        "flip_rate": r["stability"]["flip_rate"]["rate"],
        "flip_rate_ci95": ci(r["stability"]["flip_rate"]),
        "labeled_cases": agree.get("cases", 0),
        "kappa": agree.get("kappa"),
        "kappa_ci95": agree.get("kappa_ci95"),
        "accuracy": (agree.get("accuracy") or {}).get("rate"),
        "accuracy_ci95": ci(agree.get("accuracy")),
        "majority_baseline": agree.get("majority_baseline"),
        "position_consistency": (pos.get("consistency") or {}).get("rate"),
        "position_consistency_ci95": ci(pos.get("consistency")),
        "toward_padded": (pad.get("toward_padded") or {}).get("rate"),
        "toward_padded_ci95": ci(pad.get("toward_padded")),
        "reasons": r["reasons"],
    }


def _next_step(result: dict[str, Any], th: Thresholds, ws: Workspace) -> str:
    if result["trustworthy"]:
        return (
            f"export: judges {result['trustworthy']} passed; export wires a passing pointwise "
            "judge into promptfoo when its rubric.yaml entry has a `provider`"
        )
    labeled = sum(result["human_label_counts"].values())  # labels on cases the judges saw
    if labeled < th.min_labeled:
        return (
            f"a person needs to label at least {th.min_labeled} judged cases (have "
            f"{labeled}). Run `eval-builder label` (MCP: label): it picks the "
            "cases worth labeling and writes label_sheet.html for them to label offline; then "
            "`eval-builder label import <exported file>` (MCP: label_import) and run "
            "judge_check again. Never write these labels yourself"
        )
    return (
        "no judge passed; read each judge's reasons. Typical fixes: majority vote over 3 "
        "calls, run both answer orders and keep agreements, tighten the rubric wording, or "
        "try a stronger judge model, then run judge_plan and judge_check again"
    )
