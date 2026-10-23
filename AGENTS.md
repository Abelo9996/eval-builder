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
  judge/front.py   `judge-check <model>`: the one-command front door (data, run, verdict, card)
  judge/backends.py judge model backends (ollama, openai, anthropic, claude-code, codex)
  judge/sample.py  the bundled human-labeled MT-Bench sample loader
  judge/card.py    the 1200x630 reliability card (SVG, optional PNG)
  judge/plan.py    judge requests with repeated trials and swap/pad probes
  judge/run.py     opt-in judge plugin runner (off by default, runs a user command)
  judge/check.py   flip rate, kappa, accuracy, probes, verdicts
  judge/stats.py   Wilson interval, Cohen's kappa, majority vote
  data/sample/     bundled MT-Bench pairs (CC BY 4.0) used when the user gives no logs
  label.py         which cases a person should label, the CSV sheet, `label import`
  label_sheet.py   the offline HTML labeling sheet (one file, inline JS, no network)
  balance.py       the warning when cases or labels are mostly one outcome
  export.py        promptfoo, DeepEval, Inspect AI, JSONL
  report.py        report.md and report.json
  setup_agents.py  `eval-builder setup` for Claude Code, Codex, Cursor
  mcp_server.py    MCP tools over stdio
  cli.py           argparse CLI, every command supports --json
```

## Rules

- Only `judge-check <model>` (`judge/front.py` and `judge/backends.py`) calls a model:
  the judge the user names. It ships no API keys (openai/anthropic read them from the
  environment), runs local models for free, and does nothing for a paid API until `--yes`.
  Every other step makes no model or network call. (Exported files may call a model when
  the user runs them, for example the DeepEval test calling a wired judge.) The judge
  runner only starts a command the user names, and only with an explicit flag.
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
