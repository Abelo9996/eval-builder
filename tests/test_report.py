from __future__ import annotations

import json
from pathlib import Path

from eval_builder.export import export
from eval_builder.report import build_report


def test_report_sections(ready_workspace: Path) -> None:
    export(ready_workspace)
    r = build_report(ready_workspace, title="Fixture report")
    md = Path(r["report_md"]).read_text()
    for heading in (
        "# Fixture report",
        "## Sources",
        "## Redactions",
        "## Selection",
        "## Cases",
        "## Exports",
        "## Limits",
    ):
        assert heading in md
    assert "why it was picked" in md and "credit_card 1" in md
    data = json.loads(Path(r["report_json"]).read_text())
    assert data["ingest"]["traces"] == 13 and data["exports"]["cases"] == 5
    assert chr(0x2014) not in md and chr(0x2013) not in md  # no em or en dashes


def test_report_judge_table(ready_workspace: Path) -> None:
    rows = []
    for i in range(10):
        for t in range(3):
            rows.append(
                {
                    "judge": "j1",
                    "case_id": f"c{i}",
                    "mode": "pointwise",
                    "probe": "none",
                    "trial": t,
                    "verdict": "pass",
                }
            )
    (ready_workspace / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    from eval_builder.judge.check import judge_check

    judge_check(ready_workspace)
    md = Path(build_report(ready_workspace)["report_md"]).read_text()
    assert "## Judge reliability" in md and "**not_enough_data**" in md
    assert "No human labels were provided" in md
