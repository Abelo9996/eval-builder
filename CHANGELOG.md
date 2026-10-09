# Changelog

## 0.1.2 (2026-10-08)

Human labels. No judge can be called trustworthy without them, and both real agent
sessions against 0.1.0 and 0.1.1 stopped at that step: they asked for labels and had
no way to collect them.

- `label` (CLI, and MCP `label`): picks the ready cases a person should label, 24 by
  default (judge-check needs 20). The budget is split evenly across outcomes (the
  judges' consensus verdict, or the logged failure flag before any judge has run), and
  up to half of each share goes to cases where the judges disagree, flip across
  repeats or move under padding. Every pick and its reason is in `label_plan.json`.
- `label` writes `label_sheet.html`: one self-contained file that works offline and
  makes no network requests (its content security policy blocks them). One case per
  screen with the earlier turns, the reply, the expected behavior and criteria;
  pass/fail or A/B buttons (labels come from rubric.yaml), an optional note, keyboard
  shortcuts, progress, and the judges' verdicts hidden. Progress survives a reload
  through the browser's local storage. Export downloads `labels.jsonl` in exactly the
  format judge-check reads and shows the same text to copy.
- `label` also writes `label_sheet.csv` for spreadsheet users (fill the label column).
- `label import <file>` (CLI, and MCP `label_import`): reads the sheet's labels.jsonl,
  the filled-in CSV, a JSON list, or stdin (`-`); checks every case id and label
  against cases.yaml and rubric.yaml; merges into `labels.jsonl` (a new label replaces
  the same labeler's earlier one, other labelers are kept); lists rejected rows with
  the reason and exits 1 when there are any.
- `select` and `judge-check` warn, with the real proportions, when at least 80% of the
  selected cases or of the human labels share one outcome. judge-check also warns when
  a judge gave the same verdict on every labeled case or its accuracy is no better
  than always giving the most common label, and reports `majority_baseline` (that
  always-the-common-label accuracy).
- DeepEval export: a pointwise judge that passed judge-check (or one forced with
  `--judge`) now grades every case with its exact rubric.yaml prompt, through a custom
  metric in `test_eval_builder.py` and `judge.json`. Ollama providers are called on the
  local server; for other providers you fill in `call_judge`. Without a checked judge
  the file keeps GEval. The export notes and README say that Inspect AI still uses its
  default `model_graded_qa` grader.
- judge-check parses JSON verdicts that a token limit cut off mid-reason, and verdicts
  wrapped in a json code fence.
- `status` and judge-check's `next` walk through the labeling step.
- `examples/sample-labeling/`: the whole flow on the bundled 48-conversation sample.

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
