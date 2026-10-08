# Working on eval-builder

This file is for people and coding agents changing eval-builder itself. The agent
workflow for *using* the tool lives in `skills/eval-builder/SKILL.md`.

## Layout

```
src/eval_builder/
  schema.py        Trace dataclass and helpers every ingest format maps into
  ingest/          format detection and parsers (openai, anthropic, langfuse, otel, generic)
  redact.py        default-on secret and PII redaction with counts
  select.py        dedupe, near-duplicates, k-means clusters, strata, failure oversampling
  draft.py         case and rubric skeletons, validation, update_case
  judge/plan.py    judge requests with repeated trials and swap/pad probes
  judge/run.py     opt-in judge plugin runner (off by default, runs a user command)
  judge/check.py   flip rate, kappa, accuracy, probes, verdicts
  judge/stats.py   Wilson interval, Cohen's kappa, majority vote
  export.py        promptfoo, DeepEval, Inspect AI, JSONL
  report.py        report.md and report.json
  setup_agents.py  `eval-builder setup` for Claude Code, Codex, Cursor
  mcp_server.py    MCP tools over stdio
  cli.py           argparse CLI, every command supports --json
```

## Rules

- No model calls and no network access in the package. The judge runner only starts a
  command the user names, and only with an explicit flag.
- Deterministic: same inputs and seed give the same selection and the same files.
- Every number the tool reports must be traceable to a file in the workspace.
- Tests are offline, fast, and never touch the real home directory (`conftest.py`
  points HOME at a temp dir). Add a fixture when you add a format.
- Statistics changes need a test against a value computed by hand, with the arithmetic
  in a comment.
- Writing style: no em dashes or en dashes, no hype words, plain sentences.

## Commands

```
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```
