from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never let a test see or touch the real home directory."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("EVAL_BUILDER_ENABLE_JUDGE_PLUGIN", raising=False)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture
def ready_workspace(tmp_path: Path) -> Path:
    """A workspace ingested from all fixtures, selected, drafted and filled in."""
    from eval_builder.draft import draft, load_cases, update_case, write_rubric
    from eval_builder.ingest import ingest
    from eval_builder.select import select

    ws = tmp_path / "ws"
    ingest([FIXTURES], ws)
    select(ws, n=5)
    draft(ws, suite="fixture suite")
    write_rubric(
        ws,
        {
            "criteria": [
                {
                    "id": "helpful",
                    "description": "Answers the question directly.",
                    "scale": "pass_fail",
                }
            ],
            "judges": [
                {
                    "id": "j1",
                    "mode": "pointwise",
                    "criteria": ["helpful"],
                    "labels": ["pass", "fail"],
                    "prompt": "Q: {input}\nA: {output}\nExpected: {expected_behavior}\n"
                    "{criteria}\nAnswer pass or fail.",
                }
            ],
        },
    )
    for c in load_cases(ws)["cases"]:
        update_case(
            ws,
            c["id"],
            expected_behavior=f"Handles: {c['input'][:30]}",
            criteria=["helpful"],
            status="ready",
        )
    return ws
