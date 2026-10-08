"""Apply expected_behaviors.yaml and the rubric to the drafted suite through the
eval-builder API (the same calls the MCP tools update_case and set_rubric make)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from eval_builder.draft import load_cases, update_case, write_rubric

POINTWISE_PROMPT = """You are grading one reply from an AI assistant.

Earlier conversation:
{context}

Latest user message:
{input}

Assistant reply:
{output}

What a good reply does:
{expected_behavior}

Criteria:
{criteria}

Does the reply meet the expected behavior and the criteria? Answer with one word: pass or fail.
"""

RUBRIC = {
    "criteria": [
        {
            "id": "correct",
            "description": "Facts, numbers and code are correct.",
            "scale": "pass_fail",
        },
        {
            "id": "follows-instructions",
            "description": "Does what the latest user turn asks, including format constraints.",
            "scale": "pass_fail",
        },
        {
            "id": "uses-context",
            "description": "Builds on the earlier turns instead of ignoring or contradicting them.",
            "scale": "pass_fail",
        },
        {
            "id": "complete",
            "description": "Covers what was asked in enough detail to be useful.",
            "scale": "pass_fail",
        },
    ],
    "judges": [
        {
            "id": "qwen2.5-7b-pointwise",
            "mode": "pointwise",
            "criteria": ["correct", "follows-instructions", "uses-context", "complete"],
            "labels": ["pass", "fail"],
            "prompt": POINTWISE_PROMPT,
        }
    ],
}


def main(workspace: str) -> None:
    ws = Path(workspace)
    filled = yaml.safe_load((Path(__file__).parent / "expected_behaviors.yaml").read_text())
    write_rubric(ws, RUBRIC)
    done = 0
    for case in load_cases(ws)["cases"]:
        spec = filled.get(case["trace_id"])
        if spec is None:
            continue
        update_case(
            ws,
            case["id"],
            expected_behavior=spec["expected_behavior"],
            criteria=spec["criteria"],
            status="ready",
            notes="expected behavior written by the host agent (Claude Code); "
            "not reviewed by a human",
        )
        done += 1
    print(f"filled {done} cases")


if __name__ == "__main__":
    main(sys.argv[1])
