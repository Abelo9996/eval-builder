from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from eval_builder.cli import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:
    code = main([*argv, "--json"])
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_cli_end_to_end(tmp_path: Path, fixtures: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = str(tmp_path / "ws")
    code, r = run(capsys, "ingest", str(fixtures), "-w", ws)
    assert code == 0 and r["traces"] == 13
    code, r = run(capsys, "select", "-w", ws, "-n", "4")
    assert code == 0 and r["selected_count"] == 4
    code, r = run(capsys, "draft", "-w", ws)
    assert code == 0 and r["cases_added"] == 4
    code, r = run(capsys, "validate", "-w", ws)
    assert code == 1 and not r["valid"]
    code, r = run(capsys, "export", "-w", ws)
    assert code == 1 and not r["exported"]
    code, r = run(capsys, "status", "-w", ws)
    assert r["steps"]["draft"] and not r["steps"]["export"]


def test_cli_errors_are_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, r = run(capsys, "select", "-w", str(tmp_path / "nothing"))
    assert code == 2 and "run `eval-builder ingest` first" in r["error"]


def test_cli_judge_run_requires_flag(
    ready_workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EVAL_BUILDER_ENABLE_JUDGE_PLUGIN", raising=False)
    assert main(["judge-plan", "-w", str(ready_workspace)]) == 0
    assert main(["judge-run", "-w", str(ready_workspace), "--command", "j1=true"]) == 3
    assert "off by default" in capsys.readouterr().err


def test_mcp_server_lists_tools() -> None:
    from eval_builder.mcp_server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {
        "ingest",
        "select",
        "draft",
        "update_case",
        "set_rubric",
        "validate",
        "judge_plan",
        "judge_check",
        "export",
        "report",
        "status",
    } <= names
    assert "judge_run" not in names


def test_mcp_tool_call_roundtrip(tmp_path: Path, fixtures: Path) -> None:
    from eval_builder.mcp_server import build_server

    server = build_server()
    ws = str(tmp_path / "ws")
    asyncio.run(server.call_tool("ingest", {"paths": [str(fixtures)], "workspace": ws}))
    asyncio.run(server.call_tool("select", {"workspace": ws, "n": 3}))
    assert (tmp_path / "ws" / "selection.json").exists()


def test_mcp_judge_check_include_cases(ready_workspace: Path) -> None:
    from eval_builder.judge.plan import judge_plan
    from eval_builder.mcp_server import build_server

    judge_plan(ready_workspace, trials=3)
    reqs = [json.loads(x) for x in (ready_workspace / "judge_requests.jsonl").open()]
    (ready_workspace / "judgments.jsonl").write_text(
        "".join(
            json.dumps({"request_id": r["request_id"], "verdict": '{"pass": true}'}) + "\n"
            for r in reqs
        )
    )
    server = build_server()
    res = asyncio.run(
        server.call_tool("judge_check", {"workspace": str(ready_workspace), "include_cases": True})
    )
    text = json.dumps(res, default=str)
    assert '\\"majority\\": \\"pass\\"' in text or '"majority": "pass"' in text
    assert "flip_rate_ci95" in text
