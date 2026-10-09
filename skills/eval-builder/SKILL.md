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
`update_case`, `set_rubric`, `validate`, `judge_plan`, `label`, `label_import`,
`judge_check`, `export`, `report`, `status`). Otherwise use the CLI with `--json`. All steps share one
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
   clusters and a few of the reasons cases were picked. If the result has `warnings`
   (for example most picks are logged failures), pass them on: a judge checked on a
   one-sided set can look accurate by always giving the common answer.

3. **Draft and fill cases with the user.** Run `draft`, then `list_cases` to read the
   cases (input, earlier turns in `context`, logged `observed_output`). For each case, propose an
   `expected_behavior` (one or two sentences on what a good answer does) and the
   criteria it tests, then confirm with the user, especially for domain facts you are
   not sure about. Use `update_case` to save it and set `status: ready`, or
   `status: dropped` for cases that are not useful. Define criteria with `set_rubric`.
   Never mark a case ready with a guess you have not checked; ask.

4. **Validate.** Run `validate`. Fix every error it lists.

5. **Plan judge runs.** Add the user's judges to the rubric (their exact judge
   prompts, mode `pointwise` or `pairwise`, allowed labels). Run `judge_plan` with
   `trials: 5` and `probes: ["swap", "pad"]` (swap only applies to pairwise judges).
   If the user will grade in promptfoo, give each judge a `provider` (a promptfoo
   provider id such as `ollama:chat:qwen2.5:7b-instruct` or `openai:gpt-4.1-mini`)
   and have its prompt answer in JSON, `{"pass": true|false, "reason": "..."}`.
   Then the judge you check is exactly the grader promptfoo runs (step 9).

6. **Run the judges.** Each line of `judge_requests.jsonl` is one call. The fields
   you need: `request_id`, `judge` (the judge id from rubric.yaml), `trial`, `labels`
   and the rendered `prompt`. Either:
   - run each request yourself through the user's provider at the temperature they
     use in production, and append `{"request_id": ..., "verdict": ...}` lines to
     `judgments.jsonl`. The verdict may be the raw answer text or the judge's JSON;
     judge_check parses both. A short script is fine; for a local Ollama model, POST
     `{"model", "prompt", "stream": false, "options": {"temperature", "seed": trial}}`
     to `http://localhost:11434/api/generate` and use the `response` field; or
   - if the user has a judge script, ask them to run
     `eval-builder judge-run --enable-judge-plugin --command "<judge_id>=<their command>"`.
     The plugin is off by default and eval-builder ships no API keys.
   Do not change the prompt between trials. Repeated trials are the point.

7. **Human labels.** No judge can be called trustworthy without them. Run `label`
   (default 24 cases; judge_check needs at least 20). It picks the cases worth a
   person's time: both outcomes covered, and aimed at cases where the judges disagree
   or flip. It writes `label_sheet.html`, an offline page that shows one case per
   screen with pass/fail (or A/B) buttons, keyboard shortcuts and a note box, with the
   judges' verdicts hidden, plus `label_sheet.csv` for people who prefer a
   spreadsheet. Give the user the path, ask them to label every case and click
   Export (it downloads `labels.jsonl`), then run `label_import` with that file.
   Report what it returns: counts, rejected rows and any warning that the labels are
   mostly one outcome. If the user cannot label now, you can still run judge_check
   (it measures stability and bias) and export, but say plainly that no judge has been
   checked against people. **Never fill in the sheet, write labels.jsonl or present your own
   judgment as a human label.**

8. **Check the judges.** Run `judge_check`. Each judge gets one verdict:
   `trustworthy`, `unstable` (verdict flips across repeated calls), `biased` (answer
   order or irrelevant padding changes the verdict), `misaligned` (low kappa with
   human labels) or `not_enough_data`. Read the intervals, not only the point
   estimates, and repeat any `warnings` (labels mostly one outcome, a judge that gave
   the same verdict on every labeled case). Keep only trustworthy judges. For the
   others, report the reasons and suggest concrete fixes: majority vote over several
   calls, running both answer orders and only counting agreements, tighter rubric
   wording, a stronger judge model.

9. **Export.** Run `export` with the user's tool (`promptfoo`, `deepeval`, `inspect`,
   `jsonl`). The manifest lists file hashes and which judges passed. In promptfoo the
   app receives the whole conversation as chat messages, and a pointwise judge that
   passed judge_check and has a `provider` becomes the llm-rubric grader. In DeepEval
   the same judge becomes a custom metric with its exact prompt (`judge.json`; Ollama
   providers are called directly, others need `call_judge` filled in). Inspect keeps
   its default `model_graded_qa` grader. Read the `notes` in the result and pass them
   on (for example "judge X passed but has no provider").

10. **Report.** Run `report` and give the user `report.md`. Quote numbers from it
    exactly, with their intervals and sample sizes, and repeat its limits section.
    Do not round a weak result into a strong claim.

## Rules

- If the user is not available to confirm expected behavior, you may mark cases ready,
  but add a `notes` entry on each saying it was not confirmed, and say so in your answer.

- Everything stays on the machine. eval-builder makes no network calls.
- Every claim you make about a judge must come from `judge_check.json`.
- If a step fails, show the exact error and the command you ran.
