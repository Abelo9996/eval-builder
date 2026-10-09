from __future__ import annotations

import ast
import io
import json
import re
from pathlib import Path

import pytest

from eval_builder.cli import main
from eval_builder.draft import load_cases, update_case
from eval_builder.judge.check import judge_check
from eval_builder.judge.plan import judge_plan
from eval_builder.label import label, label_import, pick_cases


def _sheet_data(html: str) -> dict:
    m = re.search(r'<script id="sheet-data" type="application/json">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1))


def _judge_all(ws: Path, verdict_for: dict[str, list[str]]) -> None:
    """Write judgments: verdict_for[case_id] is the list of verdicts over the trials."""
    reqs = [json.loads(x) for x in (ws / "judge_requests.jsonl").open()]
    out = []
    for r in reqs:
        vs = verdict_for.get(r["case_id"], ["pass"])
        out.append({"request_id": r["request_id"], "verdict": vs[r["trial"] % len(vs)]})
    (ws / "judgments.jsonl").write_text("".join(json.dumps(x) + "\n" for x in out))


def test_label_writes_offline_sheet_and_csv(ready_workspace: Path) -> None:
    cid = load_cases(ready_workspace)["cases"][0]["id"]
    update_case(
        ready_workspace,
        cid,
        reference_output=None,
        notes="x",
    )
    doc = load_cases(ready_workspace)
    doc["cases"][0]["observed_output"] = "</script><script>alert(1)</script> <!-- x"
    from eval_builder.draft import CASES_HEADER
    from eval_builder.io import write_yaml

    write_yaml(ready_workspace / "cases.yaml", doc, CASES_HEADER)
    r = label(ready_workspace, n=3)
    assert r["picked"] == 3 and len(r["picks"]) == 3
    assert "label import" in r["next"] and "yourself" in r["next"]
    html = (ready_workspace / "label_sheet.html").read_text()
    # no network: nothing loaded from elsewhere, and the page forbids connections
    assert "connect-src 'none'" in html
    assert not re.search(r"""(src|href)=["']?https?:""", html)
    assert "http://" not in html and "https://" not in html
    # case text cannot close the script element
    assert html.count("</script>") == 2
    data = _sheet_data(html)
    assert len(data["cases"]) == 3
    assert {c["id"] for c in data["cases"]} == {p["case_id"] for p in r["picks"]}
    assert all(c["labels"] == ["pass", "fail"] for c in data["cases"])
    # judge verdicts and pick reasons stay out of the sheet (the labeler is blind to them)
    assert "reasons" not in json.dumps(data) and "majority" not in json.dumps(data)
    csv_text = (ready_workspace / "label_sheet.csv").read_text(encoding="utf-8-sig")
    assert csv_text.startswith("case_id,label,note,labeler,allowed_labels")
    plan = json.loads((ready_workspace / "label_plan.json").read_text())
    assert plan["picked"] == 3 and all(p["reasons"] for p in plan["picks"])


def test_label_skips_labeled_cases_and_needs_ready(ready_workspace: Path) -> None:
    cases = load_cases(ready_workspace)["cases"]
    (ready_workspace / "labels.jsonl").write_text(
        json.dumps({"case_id": cases[0]["id"], "label": "pass"}) + "\n"
    )
    r = label(ready_workspace, n=50)
    assert r["picked"] == len(cases) - 1
    assert cases[0]["id"] not in {p["case_id"] for p in r["picks"]}
    assert label(ready_workspace, n=50, include_labeled=True)["picked"] == len(cases)
    for c in cases:
        update_case(ready_workspace, c["id"], status="draft")
    with pytest.raises(ValueError, match="no cases have status: ready"):
        label(ready_workspace)


def test_pick_cases_balances_outcomes_and_prefers_disagreement() -> None:
    cases = [{"id": f"c{i:02d}", "tags": [f"cluster:{i % 3}"]} for i in range(20)]
    signals = {}
    for i, c in enumerate(cases):
        cons = "pass" if i < 4 else "fail"  # 4 pass, 16 fail
        unc = 2.5 if i in (10, 11) else 0.0
        signals[c["id"]] = {
            "consensus": cons,
            "uncertainty": unc,
            "reasons": ["judges disagree: a says fail, b says pass"] if unc else [],
        }
    picks, strata = pick_cases(cases, signals, n=8, seed=0)
    ids = {p["case_id"] for p in picks}
    assert strata == {
        "judges say fail": {"candidates": 16, "picked": 4},
        "judges say pass": {"candidates": 4, "picked": 4},
    }
    assert {"c00", "c01", "c02", "c03"} <= ids  # every rare-outcome case
    assert {"c10", "c11"} <= ids  # the disagreements
    dis = next(p for p in picks if p["case_id"] == "c10")
    assert any("judges disagree" in r for r in dis["reasons"])
    # deterministic for a seed
    assert pick_cases(cases, signals, n=8, seed=0)[0] == picks


def test_label_uses_judge_disagreement(ready_workspace: Path) -> None:
    from eval_builder.draft import load_rubric, write_rubric

    rubric = load_rubric(ready_workspace)
    j2 = dict(rubric["judges"][0], id="j2")
    write_rubric(
        ready_workspace,
        {"criteria": rubric["criteria"], "judges": [rubric["judges"][0], j2]},
    )
    judge_plan(ready_workspace, trials=3)
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    reqs = [json.loads(x) for x in (ready_workspace / "judge_requests.jsonl").open()]
    rows = []
    for r in reqs:
        v = "pass"
        if r["case_id"] == cases[0] and r["judge"] == "j2":
            v = "fail"  # j1 says pass, j2 says fail
        if r["case_id"] == cases[1]:
            v = "fail"
        rows.append({"request_id": r["request_id"], "verdict": v})
    (ready_workspace / "judgments.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    r = label(ready_workspace, n=3)
    assert r["judges"] == ["j1", "j2"]
    by_id = {p["case_id"]: p for p in r["picks"]}
    assert cases[0] in by_id and cases[1] in by_id
    assert any("judges disagree" in x for x in by_id[cases[0]]["reasons"])
    assert r["uncertain_picked"] >= 1


def test_label_import_roundtrip(ready_workspace: Path, tmp_path: Path) -> None:
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    sheet_export = tmp_path / "labels.jsonl"
    sheet_export.write_text(
        "".join(
            json.dumps(
                {
                    "case_id": cid,
                    "label": "Pass" if i % 2 else "fail",
                    "mode": "pointwise",
                    "labeler": "ana",
                    "note": "close call" if i == 0 else "",
                    "sheet": "abc",
                }
            )
            + "\n"
            for i, cid in enumerate(cases)
        )
    )
    r = label_import(ready_workspace, sheet_export)
    assert r["imported"] == len(cases) and r["rejected_count"] == 0
    rows = [json.loads(x) for x in (ready_workspace / "labels.jsonl").open()]
    assert rows[0] == {
        "case_id": cases[0],
        "label": "fail",
        "mode": "pointwise",
        "labeler": "ana",
        "note": "close call",
        "sheet": "abc",
        "source": "labels.jsonl",
    }
    assert {x["label"] for x in rows} == {"pass", "fail"}
    # a second import from the same labeler replaces, another labeler adds
    r2 = label_import(ready_workspace, sheet_export)
    assert r2["replaced"] == len(cases)
    other = tmp_path / "bo.jsonl"
    other.write_text(json.dumps({"case_id": cases[0], "label": "pass", "labeler": "bo"}) + "\n")
    label_import(ready_workspace, other)
    rows = [json.loads(x) for x in (ready_workspace / "labels.jsonl").open()]
    assert len(rows) == len(cases) + 1
    # judge-check reads the imported file as is
    judge_plan(ready_workspace, trials=3)
    _judge_all(ready_workspace, {})
    jc = judge_check(ready_workspace)
    assert jc["labeled_cases"] == len(cases) - 1  # cases[0] is a 1-1 tie between labelers


def test_label_import_csv_stdin_and_rejects(
    ready_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    label(ready_workspace, n=3)
    csv_path = ready_workspace / "label_sheet.csv"
    text = csv_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    # fill the first data row's label column the way a spreadsheet would save it
    import csv

    rows = list(csv.DictReader(io.StringIO(text)))
    rows[0]["label"] = " PASS "
    rows[1]["label"] = "maybe"
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    filled = tmp_path / "filled.csv"
    filled.write_text("﻿" + out.getvalue(), encoding="utf-8")
    assert lines  # the sheet csv was written
    code = main(["label", "import", str(filled), "-w", str(ready_workspace), "--json"])
    r = json.loads(capsys.readouterr().out)
    assert code == 1
    assert r["imported"] == 1 and r["rejected_count"] == 1 and r["skipped_blank"] == 1
    assert "not one of" in r["rejected"][0]["problem"]
    # JSON pasted on stdin
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps([{"case_id": cases[1], "label": "fail"}]))
    )
    code = main(["label", "-w", str(ready_workspace), "import", "-", "--labeler", "cy", "--json"])
    r = json.loads(capsys.readouterr().out)
    assert code == 0 and r["imported"] == 1
    rows = [json.loads(x) for x in (ready_workspace / "labels.jsonl").open()]
    assert rows[-1]["labeler"] == "cy" and rows[-1]["source"] == "stdin"
    with pytest.raises(FileNotFoundError, match="label sheet exported"):
        label_import(ready_workspace, tmp_path / "missing.jsonl")


def test_label_import_warns_on_skewed_labels(ready_workspace: Path, tmp_path: Path) -> None:
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    f = tmp_path / "l.jsonl"
    f.write_text("".join(json.dumps({"case_id": c, "label": "fail"}) + "\n" for c in cases))
    r = label_import(ready_workspace, f)
    assert any(
        "skewed" in w and f"fail {len(cases)} of {len(cases)} (100%)" in w for w in r["warnings"]
    )


def test_judge_check_warns_on_skewed_labels(ready_workspace: Path) -> None:
    judge_plan(ready_workspace, trials=3)
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    _judge_all(ready_workspace, {})  # the judge always says pass
    labels = [{"case_id": c, "label": "pass"} for c in cases[:-1]]
    labels.append({"case_id": cases[-1], "label": "fail"})
    (ready_workspace / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    r = judge_check(ready_workspace)
    n = len(cases)
    assert r["human_label_counts"] == {"pass": n - 1, "fail": 1}
    w = " ".join(r["warnings"])
    assert f"pass {n - 1} of {n}" in w and "always answers 'pass'" in w
    assert "gave the same verdict, 'pass', on all" in w
    s = r["summary"][0]
    assert s["majority_baseline"] == round((n - 1) / n, 4)


def test_judge_check_warns_when_accuracy_is_only_the_baseline(ready_workspace: Path) -> None:
    judge_plan(ready_workspace, trials=3)
    cases = [c["id"] for c in load_cases(ready_workspace)["cases"]]
    assert len(cases) == 5
    # humans: pass on 1 case, fail on 4; judge: pass on 2 (one right, one wrong)
    _judge_all(
        ready_workspace, {cases[0]: ["pass"], cases[1]: ["pass"]} | {c: ["fail"] for c in cases[2:]}
    )
    labels = [{"case_id": cases[0], "label": "pass"}]
    labels += [{"case_id": c, "label": "fail"} for c in cases[1:]]
    (ready_workspace / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    r = judge_check(ready_workspace)
    # accuracy 4/5 = baseline 4/5 (always 'fail')
    assert any("no better than always answering 'fail' (80%)" in w for w in r["warnings"])


def test_select_warns_when_picks_are_mostly_failures() -> None:
    from eval_builder.select import selection_warnings

    res = {
        "population": {"failures_unique": 11},
        "selected_count": 10,
        "selected_failures": 8,
    }
    (w,) = selection_warnings(res)
    assert "logged failures 8 of 10 (80%), no failure logged 2 (20%)" in w
    assert "always says fail" in w
    assert selection_warnings({**res, "selected_failures": 5}) == []
    # no failure signal in the logs at all: nothing to warn about
    assert selection_warnings({**res, "population": {"failures_unique": 0}}) == []


def test_deepeval_export_wires_checked_judge(ready_workspace: Path) -> None:
    from eval_builder.draft import load_rubric, write_rubric
    from eval_builder.export import DEEPEVAL_TEST, export

    rubric = load_rubric(ready_workspace)
    rubric["judges"][0]["provider"] = {
        "id": "ollama:chat:qwen2.5:7b-instruct",
        "config": {"temperature": 0},
    }
    write_rubric(ready_workspace, {k: v for k, v in rubric.items() if k != "version"})
    out = ready_workspace / "exports" / "deepeval"
    r = export(ready_workspace, ["deepeval"])
    assert r["deepeval_grader"] is None and not (out / "judge.json").exists()
    assert any("GEval" in n for n in r["notes"])
    (ready_workspace / "judge_check.json").write_text(
        json.dumps(
            {
                "summary": [{"judge": "j1", "verdict": "trustworthy"}],
                "trustworthy": ["j1"],
                "thresholds": {},
            }
        )
    )
    r = export(ready_workspace, ["deepeval", "inspect"])
    assert r["deepeval_grader"]["judge"] == "j1"
    assert any("Inspect AI" in n and "model_graded_qa" in n for n in r["notes"])
    judge = json.loads((out / "judge.json").read_text())
    assert judge["prompt"] == rubric["judges"][0]["prompt"]
    assert judge["judge_check_verdict"] == "trustworthy"
    ds = json.loads((out / "dataset.json").read_text())
    assert "context_text" in ds[0]["additional_metadata"]
    # the generated verdict parser understands the answers judge-check understood
    tree = ast.parse(DEEPEVAL_TEST)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_verdict")
    ns: dict = {"json": json, "re": re}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "t", "exec"), ns)
    pv = ns["parse_verdict"]
    assert pv('{"pass": false, "reason": "no"}') == "fail"
    assert pv('```json\n{"pass": true}\n```') == "pass"
    assert pv('{"pass": true, "reason": "cut off') == "pass"
    assert pv("Pass.") == "pass"
    # a judge that no longer passes is removed on the next export
    (ready_workspace / "judge_check.json").unlink()
    export(ready_workspace, ["deepeval"])
    assert not (out / "judge.json").exists()


def test_cli_label_and_status(ready_workspace: Path, capsys) -> None:
    from eval_builder.status import status

    judge_plan(ready_workspace, trials=3)
    _judge_all(ready_workspace, {})
    assert status(ready_workspace)["next"].startswith("eval-builder label ")
    code = main(["label", "-w", str(ready_workspace), "-n", "2"])
    out = capsys.readouterr().out
    assert code == 0 and "picked 2 of" in out and "label_sheet.html" in out
    assert "label_sheet.html in a browser" in status(ready_workspace)["next"]


def test_mcp_lists_label_tools() -> None:
    import asyncio

    from eval_builder.mcp_server import build_server

    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert {"label", "label_import"} <= names
