from __future__ import annotations

from pathlib import Path

import pytest

from eval_builder.draft import draft, load_cases, update_case, validate, write_rubric
from eval_builder.ingest import ingest
from eval_builder.select import select


def _drafted(tmp_path: Path, fixtures: Path) -> Path:
    ws = tmp_path / "ws"
    ingest([fixtures], ws)
    select(ws, n=4)
    draft(ws)
    return ws


def test_draft_writes_todo_skeletons_that_fail_validation(tmp_path: Path, fixtures: Path) -> None:
    ws = _drafted(tmp_path, fixtures)
    cases = load_cases(ws)["cases"]
    assert len(cases) == 4
    assert all(c["status"] == "draft" and "TODO" in c["expected_behavior"] for c in cases)
    assert all(c["selected_because"] for c in cases)
    v = validate(ws)
    assert not v["valid"]
    problems = {e["problem"] for e in v["errors"]}
    assert "no cases have status: ready" in problems
    assert "missing or still TODO" in problems  # rubric skeleton


def test_ready_case_with_todo_is_rejected(tmp_path: Path, fixtures: Path) -> None:
    ws = _drafted(tmp_path, fixtures)
    write_rubric(ws, {"criteria": [{"id": "c1", "description": "Correct."}]})
    cid = load_cases(ws)["cases"][0]["id"]
    update_case(ws, cid, status="ready")
    v = validate(ws)
    assert {"where": f"cases[{cid}].expected_behavior", "problem": "missing or still TODO"} in v[
        "errors"
    ]
    update_case(ws, cid, expected_behavior="Gives the exact steps.", criteria=["c1"])
    v = validate(ws)
    assert v["valid"] and v["counts"]["ready"] == 1 and v["warnings"]


def test_unknown_criterion_and_bad_status(tmp_path: Path, fixtures: Path) -> None:
    ws = _drafted(tmp_path, fixtures)
    write_rubric(ws, {"criteria": [{"id": "c1", "description": "Correct."}]})
    cid = load_cases(ws)["cases"][0]["id"]
    update_case(ws, cid, expected_behavior="x", criteria=["nope"], status="ready")
    assert any("unknown criterion nope" in e["problem"] for e in validate(ws)["errors"])
    with pytest.raises(ValueError):
        update_case(ws, cid, status="done")
    with pytest.raises(ValueError):
        update_case(ws, cid, input="changed")
    with pytest.raises(KeyError):
        update_case(ws, "case-999", status="ready")


def test_redraft_keeps_filled_cases(tmp_path: Path, fixtures: Path) -> None:
    ws = _drafted(tmp_path, fixtures)
    cid = load_cases(ws)["cases"][0]["id"]
    update_case(ws, cid, expected_behavior="Kept.", status="ready")
    select(ws, n=6)
    r = draft(ws)
    cases = {c["id"]: c for c in load_cases(ws)["cases"]}
    assert cases[cid]["expected_behavior"] == "Kept."
    assert r["cases_total"] >= 4 and not r["rubric_created"]


def test_rubric_judge_validation(tmp_path: Path, fixtures: Path) -> None:
    ws = _drafted(tmp_path, fixtures)
    r = write_rubric(
        ws,
        {
            "criteria": [{"id": "c1", "description": "ok"}],
            "judges": [{"id": "j", "mode": "listwise", "criteria": ["c2"]}],
        },
    )
    problems = " ".join(e["problem"] for e in r["errors"])
    assert "must be one of" in problems and "unknown criterion c2" in problems
    assert "verdict labels" in problems
