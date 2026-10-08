# Changelog

## 0.1.1 (2026-10-08)

Fixes from a fresh-install audit and a real Claude Code session driving the MCP server.

- promptfoo export: the app now receives the whole conversation as chat messages
  (`{{ messages | dump }}`). Before, only the last user turn was sent, so multi-turn cases
  such as "Can you parallelize it?" reached the app without their context.
- promptfoo export wires a checked judge in as the llm-rubric grader: the first pointwise
  judge that judge-check marked trustworthy and that has a new optional `provider` field in
  rubric.yaml (a promptfoo provider id). `export --judge <id>` forces one, with a warning
  when it did not pass. The judge's exact prompt becomes `rubricPrompt`.
- judge-check parses JSON verdicts such as `{"pass": false, "reason": "..."}`, so one judge
  prompt works both in judge-check and as a promptfoo grader.
- judge-check summary rows (CLI `--json` and MCP) now carry 95% intervals, case counts and
  label counts, and the result has a `next` step (for example how to write labels.jsonl).
- judge-plan documents the request row fields (`judge`, not `judge_id`), refuses to plan
  when no case is ready or a judge is still TODO, and says how to write judgments.
- Clearer errors and next steps: judge-check without judgments, format detection failure
  (shows the keys it saw and the shapes it accepts), `select` when fewer unique traces than
  `-n` exist, `status` now walks through every step including judges.
- MCP `judge_check` takes `include_cases` to return per-case verdict counts and majorities.
- MCP tool descriptions say what each tool does, when to use it and what to call next.
- `setup`: installs the Codex skill in the same run when the codex CLI is on PATH but
  `~/.codex` does not exist yet, and says to restart the agent after applying.
- `examples/sample_logs.jsonl`: 48 conversations from MT-Bench (CC BY 4.0) to try the
  quickstart without your own logs.

## 0.1.0 (2026-10-08)

First release.

- `ingest`: OpenAI chat JSONL (fine-tuning style and request/response logs), Anthropic
  messages, Langfuse trace exports, OpenTelemetry GenAI spans (OTLP JSON and flat span
  JSON), and generic input/output JSONL. Default-on redaction with a per-kind report.
- `select`: exact and near-duplicate removal, TF-IDF k-means clusters, stratum
  coverage, failure oversampling, a recorded reason for every pick.
- `draft`, `validate`: case and rubric templates that the agent fills in with the user.
- `judge-plan`, `judge-run` (opt-in), `judge-check`: repeated trials, flip rate,
  agreement with human labels (accuracy with Wilson intervals, Cohen's kappa), answer
  order and padding probes, a verdict per judge.
- `export`: promptfoo, DeepEval, Inspect AI, JSONL.
- `report`: Markdown and JSON.
- `setup`: registers the MCP server with Claude Code, Codex and Cursor.
