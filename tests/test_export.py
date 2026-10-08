from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

from eval_builder.draft import load_cases, update_case
from eval_builder.export import export
from eval_builder.io import sha256_file


def test_export_refuses_invalid(tmp_path: Path, ready_workspace: Path) -> None:
    cid = load_cases(ready_workspace)["cases"][0]["id"]
    update_case(ready_workspace, cid, expected_behavior="TODO later")
    r = export(ready_workspace)
    assert r["exported"] is False and r["validation"]["errors"]
    assert not (ready_workspace / "exports" / "manifest.json").exists()


def test_export_all_formats(ready_workspace: Path) -> None:
    cases = load_cases(ready_workspace)["cases"]
    update_case(ready_workspace, cases[-1]["id"], status="dropped")
    r = export(ready_workspace)
    assert r["exported"] and r["cases"] == len(cases) - 1
    out = ready_workspace / "exports"
    n = r["cases"]

    # promptfoo: valid YAML with one llm-rubric test per case
    cfg = yaml.safe_load((out / "promptfoo" / "promptfooconfig.yaml").read_text())
    assert cfg["prompts"] == ["{{ messages | dump }}"] and cfg["providers"] == ["echo"]
    assert "defaultTest" not in cfg  # no judge passed, so no grader is wired in
    assert len(cfg["tests"]) == n
    t0 = cfg["tests"][0]
    assert t0["assert"][0]["type"] == "llm-rubric" and "Criteria:" in t0["assert"][0]["value"]
    assert t0["vars"]["input"] and t0["metadata"]["case_id"].startswith("case-")

    # deepeval: dataset fields and a test file that parses
    ds = json.loads((out / "deepeval" / "dataset.json").read_text())
    assert len(ds) == n
    assert set(ds[0]) >= {
        "name",
        "input",
        "expected_output",
        "actual_output",
        "additional_metadata",
    }
    ast.parse((out / "deepeval" / "test_eval_builder.py").read_text())

    # inspect: id/input/target per sample, and a task file that parses
    rows = [json.loads(x) for x in (out / "inspect" / "dataset.jsonl").open()]
    assert len(rows) == n and all({"id", "input", "target", "metadata"} <= set(r) for r in rows)
    assert all(r["target"] for r in rows)
    ast.parse((out / "inspect" / "task.py").read_text())

    # jsonl
    plain = [json.loads(x) for x in (out / "jsonl" / "cases.jsonl").open()]
    assert len(plain) == n and plain[0]["criteria"][0]["id"] == "helpful"

    # manifest hashes match the files
    for f in r["files"]:
        assert sha256_file(ready_workspace / f["path"]) == f["sha256"]


def test_inspect_multi_turn_input_is_message_list(ready_workspace: Path) -> None:
    cid = load_cases(ready_workspace)["cases"][0]["id"]
    doc = load_cases(ready_workspace)
    doc["cases"][0]["context"] = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
    ]
    from eval_builder.draft import CASES_HEADER
    from eval_builder.io import write_yaml

    write_yaml(ready_workspace / "cases.yaml", doc, CASES_HEADER)
    export(ready_workspace, ["inspect", "promptfoo"])
    rows = {
        json.loads(x)["id"]: json.loads(x)
        for x in (ready_workspace / "exports" / "inspect" / "dataset.jsonl").open()
    }
    msgs = rows[cid]["input"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    cfg = yaml.safe_load(
        (ready_workspace / "exports" / "promptfoo" / "promptfooconfig.yaml").read_text()
    )
    # the app gets the whole conversation, not only the last user turn
    v = cfg["tests"][0]["vars"]
    assert [m["role"] for m in v["messages"]] == ["user", "assistant", "user"]
    assert v["messages"][0]["content"] == "first" and v["messages"][-1]["content"] == v["input"]
    assert v["context"] == "user: first\n\nassistant: reply"


def _trust(ws: Path, judge: str) -> None:
    """Write a judge_check.json that marks `judge` trustworthy (export only reads verdicts)."""
    (ws / "judge_check.json").write_text(
        json.dumps(
            {
                "summary": [{"judge": judge, "verdict": "trustworthy"}],
                "trustworthy": [judge],
                "thresholds": {},
            }
        )
    )


def _set_judge(ws: Path, **fields: object) -> None:
    from eval_builder.draft import load_rubric, write_rubric

    rubric = load_rubric(ws)
    rubric["judges"][0].update(fields)
    write_rubric(ws, {k: v for k, v in rubric.items() if k != "version"})


def test_promptfoo_wires_trusted_judge_as_grader(ready_workspace: Path) -> None:
    prompt = (
        "Conversation: {context}\nUser: {input}\nReply: {output}\nGood reply: "
        '{expected_behavior}\n{criteria}\nAnswer JSON: {"pass": true|false, "reason": "..."}'
    )
    _set_judge(ready_workspace, provider="ollama:chat:qwen2.5:7b-instruct", prompt=prompt)
    _trust(ready_workspace, "j1")
    r = export(ready_workspace, ["promptfoo"])
    assert r["promptfoo_grader"] == {
        "judge": "j1",
        "provider": "ollama:chat:qwen2.5:7b-instruct",
        "verdict": "trustworthy",
    }
    assert r["notes"] == []
    cfg = yaml.safe_load(
        (ready_workspace / "exports" / "promptfoo" / "promptfooconfig.yaml").read_text()
    )
    opts = cfg["defaultTest"]["options"]
    assert opts["provider"] == "ollama:chat:qwen2.5:7b-instruct"
    rp = opts["rubricPrompt"]
    # placeholders become promptfoo vars, literal braces stay inside raw blocks
    for var in ("context", "input", "output", "expected_behavior", "criteria"):
        assert "{{ " + var + " }}" in rp
    assert '{% raw %}\nAnswer JSON: {"pass": true|false, "reason": "..."}{% endraw %}' in rp
    assert set(cfg["tests"][0]["vars"]) >= {"expected_behavior", "criteria", "context"}


def test_promptfoo_grader_notes(ready_workspace: Path) -> None:
    # trusted but no provider: not wired, and the note says how to fix it
    _trust(ready_workspace, "j1")
    r = export(ready_workspace, ["promptfoo"])
    assert r["promptfoo_grader"] is None
    assert any("no `provider`" in n for n in r["notes"])
    # forced judge that did not pass and answers with a bare word: wired, with two warnings
    _set_judge(ready_workspace, provider="openai:gpt-4.1-mini")
    (ready_workspace / "judge_check.json").unlink()
    r = export(ready_workspace, ["promptfoo"], judge="j1")
    assert r["promptfoo_grader"]["verdict"] is None
    assert any("not checked" in n for n in r["notes"])
    assert any("does not ask for JSON" in n for n in r["notes"])


def test_export_unknown_format(ready_workspace: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        export(ready_workspace, ["csv"])
