"""Markdown and JSON report over whatever steps have run in a workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .balance import proportions
from .draft import load_cases
from .io import read_json, write_json
from .workspace import Workspace

STATIC_LIMITS = [
    "Selection is lexical (TF-IDF over the user input). Two inputs that mean the same thing "
    "in different words can land in different clusters, and near-duplicate detection only "
    "catches close textual matches.",
    "Redaction is pattern-based (emails, common API key formats, Luhn-valid card numbers, "
    "US-style phone numbers, SSN-shaped numbers). Names, addresses and free-form secrets are "
    "not detected. Review traces before sharing them.",
    "eval-builder does not write expected behavior. Cases are only as good as what the agent "
    "and user put in cases.yaml.",
    "Judge verdicts depend on the thresholds shown and on how many cases, trials and human "
    "labels were provided. Small samples give wide intervals; read the intervals, not just "
    "the point estimates.",
    "The bias probes cover answer order and irrelevant padding only. They do not detect "
    "self-preference, style bias or rubric misreadings.",
]


_DEDUPE_LABEL = {"input": "the user turns", "input+output": "the user turns plus the output"}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _ci(r: dict[str, Any] | None) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    lo, hi = r["ci95"]
    return f"{r['rate']:.0%} [{lo:.0%}, {hi:.0%}] (n={r['n']})"


def _md_escape(s: Any) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def build_report(workspace: str | Path, title: str | None = None) -> dict[str, Any]:
    ws = Workspace.at(workspace)
    data: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "eval_builder_version": __version__,
        "workspace": str(ws.root),
    }
    if ws.ingest_report.exists():
        data["ingest"] = read_json(ws.ingest_report)
    if ws.selection.exists():
        data["selection"] = read_json(ws.selection)
    if ws.cases.exists():
        cases = load_cases(ws.root).get("cases") or []
        data["cases"] = {
            "total": len(cases),
            "by_status": {
                s: sum(1 for c in cases if c.get("status") == s)
                for s in ("draft", "ready", "dropped")
            },
        }
    if ws.judge_check.exists():
        data["judge_check"] = read_json(ws.judge_check)
    manifest = ws.exports / "manifest.json"
    if manifest.exists():
        data["exports"] = read_json(manifest)
    run_log = ws.root / "judge_run_log.json"
    if run_log.exists():
        data["judge_run"] = read_json(run_log)
    data["limits"] = list(STATIC_LIMITS) + _dynamic_limits(data)
    write_json(ws.report_json, data)
    ws.report_md.write_text(render_markdown(data, title), encoding="utf-8")
    return {
        "report_md": str(ws.report_md),
        "report_json": str(ws.report_json),
        "sections": [
            k for k in ("ingest", "selection", "cases", "judge_check", "exports") if k in data
        ],
    }


def _dynamic_limits(data: dict[str, Any]) -> list[str]:
    out = []
    jc = data.get("judge_check")
    if jc and not jc.get("labels_file"):
        out.append("No human labels were provided, so no judge can be marked trustworthy.")
    sel = data.get("selection")
    if sel and sel["population"]["failures_unique"] == 0:
        out.append(
            "No traces carried an error flag or negative feedback, so failure "
            "oversampling had nothing to work with."
        )
    return out


def render_markdown(d: dict[str, Any], title: str | None = None) -> str:
    L: list[str] = [f"# {title or 'eval-builder report'}", ""]
    L.append(f"Generated {d['generated_at']} by eval-builder {d['eval_builder_version']}.")
    L.append("")
    ing = d.get("ingest")
    if ing:
        L += [
            "## Sources",
            "",
            "| file | format | sha256 | records | traces | skipped |",
            "|---|---|---|---|---|---|",
        ]
        for s in ing["sources"]:
            skipped = ", ".join(f"{k}: {v}" for k, v in s["skipped"].items()) or "0"
            L.append(
                f"| {_md_escape(Path(s['path']).name)} | {s['format']} | "
                f"`{s['sha256'][:16]}` | {s['records']} | {s['traces']} | "
                f"{_md_escape(skipped)} |"
            )
        L += [
            "",
            f"Traces ingested: {ing['traces']} ({ing['multi_turn']} multi-turn, "
            f"{ing['with_error']} with an error flag). Feedback: "
            + ", ".join(f"{k} {v}" for k, v in ing["feedback"].items())
            + ".",
            "",
        ]
        r = ing["redactions"]
        L += ["## Redactions", ""]
        if not r["enabled"]:
            L.append("Redaction was turned off for this run.")
        elif r["total"] == 0:
            L.append("Redaction was on. No matches.")
        else:
            L.append(
                f"Redaction was on. {r['total']} value(s) replaced in "
                f"{r['traces_affected']} trace(s): "
                + ", ".join(f"{k} {v}" for k, v in r["by_kind"].items())
                + "."
            )
        L.append("")
    sel = d.get("selection")
    if sel:
        p = sel["population"]
        L += [
            "## Selection",
            "",
            f"{p['traces']} traces, {p['exact_duplicates_removed']} exact duplicates removed, "
            f"{p['near_duplicates_merged']} near-duplicates merged (cosine >= "
            f"{sel['params']['near_dup_threshold']} on "
            f"{_DEDUPE_LABEL.get(sel['params']['dedupe_on'], sel['params']['dedupe_on'])}), "
            f"{p['unique']} unique. Selected {sel['selected_count']} "
            f"({sel['selected_failures']} failures; failures are {p['failures_unique']} of "
            f"{p['unique']} unique traces). Seed {sel['params']['seed']}, "
            f"{sel['params']['clusters']} k-means clusters.",
            "",
            "| cluster | traces | share | selected | top terms |",
            "|---|---|---|---|---|",
        ]
        for c in sel["clusters"]:
            L.append(
                f"| {c['id']} | {c['size']} | {c['share']:.0%} | {c['selected']} | "
                f"{_md_escape(', '.join(c['terms']))} |"
            )
        if sel.get("strata"):
            L += ["", "| stratum | value | unique traces | selected |", "|---|---|---|---|"]
            for f, vals in sel["strata"].items():
                for v, cnt in vals.items():
                    L.append(f"| {f} | {_md_escape(v)} | {cnt['population']} | {cnt['selected']} |")
        if sel.get("strata_skipped"):
            L.append("")
            L.append(
                "Not stratified: "
                + ", ".join(f"{k} ({v})" for k, v in sel["strata_skipped"].items())
            )
        L += ["", "| trace | cluster | represents | why it was picked |", "|---|---|---|---|"]
        for s in sel["selected"]:
            L.append(
                f"| `{s['trace_id']}` | {s['cluster']} | {s['represents']} | "
                f"{_md_escape('; '.join(s['reasons']))} |"
            )
        L.append("")
    cs = d.get("cases")
    if cs:
        b = cs["by_status"]
        L += [
            "## Cases",
            "",
            f"{cs['total']} cases: {b['ready']} ready, {b['draft']} draft, {b['dropped']} dropped.",
            "",
        ]
    jc = d.get("judge_check")
    if jc:
        L += ["## Judge reliability", ""]
        th = jc["thresholds"]
        L.append(
            f"Thresholds: flip rate <= {th['max_flip_rate']:.0%} (cases with >= "
            f"{th['min_trials']} trials, >= {th['min_cases']} cases), position "
            f"consistency >= {th['min_position_consistency']:.0%}, padding moves verdict "
            f"toward padded answer <= {th['max_toward_padded_rate']:.0%}, Cohen's kappa "
            f">= {th['min_kappa']} on >= {th['min_labeled']} human-labeled cases. Intervals "
            f"are 95% (Wilson for rates, Cohen's large-sample SE for kappa). Self-agreement is "
            "the chance one call matches the judge's own majority; majority-of-3 stable is "
            "the chance a 3-call majority vote matches it (exact, needs >= 5 trials)."
        )
        L += [
            "",
            "| judge | mode | verdict | flip rate | self-agreement | majority-of-3 stable | "
            "accuracy vs humans | kappa | position consistency | first-shown picked | "
            "padding helped |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for jid, r in jc["judges"].items():
            st, ag = r["stability"], r["human_agreement"] or {}
            pos, verb = r["position_probe"] or {}, r["verbosity_probe"] or {}
            kappa = "n/a"
            if ag.get("kappa") is not None:
                kappa = f"{ag['kappa']:.2f}"
                if ag.get("kappa_ci95"):
                    kappa += f" [{ag['kappa_ci95'][0]:.2f}, {ag['kappa_ci95'][1]:.2f}]"
            L.append(
                f"| {_md_escape(jid)} | {r['mode']} | **{r['verdict']}** | "
                f"{_ci(st['flip_rate'])} | {_pct(st['mean_self_agreement'])} | "
                f"{_pct(st.get('majority_of_3_stability'))} | "
                f"{_ci(ag.get('accuracy'))} | {kappa} | {_ci(pos.get('consistency'))} | "
                f"{_ci(pos.get('first_position_rate'))} | {_ci(verb.get('toward_padded'))} |"
            )
        L.append("")
        for jid, r in jc["judges"].items():
            L.append(
                f"- **{jid}** ({r['verdict']}): "
                + " ".join(s.rstrip(".") + "." for s in r["reasons"])
            )
        L.append("")
        hl = {k: v for k, v in (jc.get("human_label_counts") or {}).items() if v}
        if hl:
            top = max(hl.values()) / sum(hl.values())
            L += [
                f"Human labels on judged cases: {proportions(hl)}. A judge that always gave "
                f"the most common label would score {top:.0%} accuracy, which is the bar "
                "accuracy has to clear; kappa already corrects for it.",
                "",
            ]
        for w in jc.get("warnings") or []:
            L.append(f"- Warning: {_md_escape(w)}")
        if jc.get("warnings"):
            L.append("")
    run = d.get("judge_run")
    if run:
        L += ["Judge calls made through the opt-in judge plugin (`judge-run`):", ""]
        for i, rr in enumerate(run.get("runs", [run]), 1):
            for jid, e in rr["judges"].items():
                if not e["requests"]:
                    continue
                L.append(
                    f"- run {i}, {jid}: `{_md_escape(e['command'])}`, {e['ok']} ok, "
                    f"{e['errors']} errors, {e['seconds']} s"
                )
        L.append("")
    ex = d.get("exports")
    if ex:
        L += [
            "## Exports",
            "",
            f"{ex['cases']} ready cases exported.",
            "",
            "| file | sha256 |",
            "|---|---|",
        ]
        for f in ex["files"]:
            L.append(f"| {f['path']} | `{f['sha256'][:16]}` |")
        L.append("")
    L += ["## Limits", ""] + [f"- {x}" for x in d["limits"]] + [""]
    return "\n".join(L)
