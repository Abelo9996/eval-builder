# Changelog

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
