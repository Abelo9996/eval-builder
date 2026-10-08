---
name: eval-builder
description: Turn an app's real LLM logs (OpenAI chat JSONL, Anthropic messages, Langfuse exports, OpenTelemetry GenAI spans, or input/output JSONL) into an eval suite, measure which LLM judges can be trusted (flip rate, agreement with human labels, position and length bias), and export to promptfoo, DeepEval, Inspect AI or JSONL. Use when the user wants evals from production traces, wants to know whether an LLM-as-a-judge is reliable, or wants regression tests from real conversations.
---

# eval-builder

eval-builder is a local, deterministic tool. It never calls a model. You (the agent)
are the brain: you write expected behavior with the user, you run judges through the
user's own provider, and eval-builder does the bookkeeping, the selection and the
statistics, and records evidence for every step.

Use the MCP tools when they are available (`ingest`, `select`, `draft`, `list_cases`,
`update_case`, `set_rubric`, `validate`, `judge_plan`, `judge_check`, `export`,
`report`, `status`). Otherwise use the CLI with `--json`. All steps share one
workspace directory (default `./evalset`).

## Workflow

1. **Ingest.** Ask where the logs are. Run `ingest` on the files or folder. Redaction
   of emails, API keys, card numbers, phone numbers and SSN-shaped numbers is on by
   default. Tell the user how many traces were read, how many were skipped and why,
   and what was redacted (counts by kind). Do not turn redaction off unless the user
   asks.

2. **Select.** Run `select` with `n` around 30 to 50. Pass `stratify` with the
   metadata keys that matter to the user (route, feature, customer tier, model).
   Failures (error flags, negative feedback) are oversampled. Show the user the
   clusters and a few of the reasons cases were picked.

3. **Draft and fill cases with the user.** Run `draft`. For each case, propose an
   `expected_behavior` (one or two sentences on what a good answer does) and the
   criteria it tests, then confirm with the user, especially for domain facts you are
   not sure about. Use `update_case` to save it and set `status: ready`, or
   `status: dropped` for cases that are not useful. Define criteria with `set_rubric`.
   Never mark a case ready with a guess you have not checked; ask.

4. **Validate.** Run `validate`. Fix every error it lists.

5. **Plan judge runs.** Add the user's judges to the rubric (their exact judge
   prompts, mode `pointwise` or `pairwise`, allowed labels). Run `judge_plan` with
   `trials: 5` and `probes: ["swap", "pad"]` (swap only applies to pairwise judges).

6. **Run the judges.** Each row of `judge_requests.jsonl` is one call, with the
   rendered `prompt`. Either:
   - run each request yourself through the user's provider at the temperature they
     use in production, and append `{"request_id": ..., "verdict": ...}` rows to
     `judgments.jsonl`; or
   - if the user has a judge script, ask them to run
     `eval-builder judge-run --enable-judge-plugin --command "<judge_id>=<their command>"`.
     The plugin is off by default and eval-builder ships no API keys.
   Do not change the prompt between trials. Repeated trials are the point.

7. **Human labels.** Ask the user to label at least 20 cases (more is better) in
   `labels.jsonl` as `{"case_id": ..., "label": ...}`. **Never write human labels
   yourself and never present your own judgment as a human label.** Without labels,
   no judge can be called trustworthy, and the report says so.

8. **Check the judges.** Run `judge_check`. Each judge gets one verdict:
   `trustworthy`, `unstable` (verdict flips across repeated calls), `biased` (answer
   order or irrelevant padding changes the verdict), `misaligned` (low kappa with
   human labels) or `not_enough_data`. Read the intervals, not only the point
   estimates. Keep only trustworthy judges. For the others, report the reasons and
   suggest concrete fixes: majority vote over several calls, running both answer
   orders and only counting agreements, tighter rubric wording, a stronger judge model.

9. **Export.** Run `export` with the user's tool (`promptfoo`, `deepeval`, `inspect`,
   `jsonl`). The manifest lists file hashes and which judges passed.

10. **Report.** Run `report` and give the user `report.md`. Quote numbers from it
    exactly, with their intervals and sample sizes, and repeat its limits section.
    Do not round a weak result into a strong claim.

## Rules

- Everything stays on the machine. eval-builder makes no network calls.
- Every claim you make about a judge must come from `judge_check.json`.
- If a step fails, show the exact error and the command you ran.
