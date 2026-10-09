# Labeling example

The human-labeling step, end to end, on the 48 conversations in
[`../sample_logs.jsonl`](../sample_logs.jsonl) (16 MT-Bench questions, each answered
by gpt-4, alpaca-13b and llama-13b; CC BY 4.0). Everything here was produced by
[`run.sh`](run.sh) on an Apple M4 MacBook (16 GB) on October 8 and 9, 2026, with
eval-builder 0.1.2 from this repository.

**Who labeled.** The labels in [`evalset/labels.jsonl`](evalset/labels.jsonl) were made
by the developer, not by an independent annotator: Claude Code, working for the
developer, read each picked case in full (earlier turns, reply, expected behavior) and
recorded a decision with a note for the close calls ([`decisions.json`](decisions.json)).
[`drive_sheet.py`](drive_sheet.py) then entered those decisions through the real
`label_sheet.html` in headless Chrome, using the keyboard shortcuts, and clicked Export.
The expected behavior in [`fill.py`](fill.py) was written the same way. Treat the
numbers below as a demonstration of the flow, not as ground truth about these judges.

## Steps and what they printed

1. `select --dedupe-on input+output --near-dup 0.99` kept each model's answer: 48
   traces, 47 unique (two answers to one question were near-identical). All 47 became
   ready cases with one expected behavior per question.
2. Three local judges through Ollama (`examples/judges/ollama_judge.py`), one pass/fail
   prompt that answers in JSON, 5 trials per case plus 3 with an irrelevant paragraph
   appended to the reply: 1,128 calls, 0 errors (qwen2.5:7b-instruct at temperature
   0.8: 1,114 s; the same model at temperature 0: 1,130 s; llama3.2:3b: 589 s; the
   machine was shared with other jobs).
3. `judge-check` without labels: llama3.2-3b `unstable` (verdict changed across repeats
   on 47% of cases), both qwen judges `not_enough_data` ("stable, but only 0 case(s)
   have human labels").
4. `label` picked 24 of the 47 cases: 12 where the judges' consensus was fail and 12
   where it was pass; 15 of the 24 are cases where judges disagree, flip or move under
   padding ([`evalset/label_plan.json`](evalset/label_plan.json) has every reason).
5. The sheet in headless Chrome ([`sheet-run/drive_log.txt`](sheet-run/drive_log.txt)):
   24 cases, a reload after 13 labels kept "13 of 24 labeled", the download
   (`labels.jsonl`, 4,292 bytes) was identical to the copy box, 2 requests in total,
   none of them to anything but `file:`, `blob:` or `data:` URLs, no console errors. Screenshots:
   [first case](sheet-run/sheet-first-case.png), [phone width](sheet-run/sheet-phone.png),
   [export](sheet-run/sheet-export.png).
6. `label import`: 24 imported, 0 rejected; labels fail 18, pass 6.
7. `judge-check` with the labels ([`evalset/report.md`](evalset/report.md)):

| judge | verdict | flip rate | accuracy vs labels | kappa | padding helped |
|---|---|---|---|---|---|
| qwen2.5:7b-instruct, temp 0 | trustworthy | 0% [0%, 8%] | 75% [55%, 88%] | 0.50 [0.15, 0.85] | 0% [0%, 8%] |
| qwen2.5:7b-instruct, temp 0.8 | trustworthy | 9% [3%, 20%] | 71% [51%, 85%] | 0.44 [0.09, 0.79] | 0% [0%, 8%] |
| llama3.2:3b | unstable | 47% [33%, 61%] | 54% [35%, 72%] | 0.12 [-0.26, 0.50] | 4% [1%, 14%] |

n = 47 cases for flip rate and padding, 24 labeled cases for accuracy and kappa;
brackets are 95% intervals.

## What it shows, read plainly

- Both qwen judges clear the default thresholds (kappa at least 0.4 on at least 20
  labels), so the export wires `qwen2.5-7b` (the first that passed) into promptfoo and
  DeepEval. The kappa intervals are wide, from about 0.1 to 0.8: 24 labels cannot pin
  the agreement down.
- Their accuracy (71% and 75%) is no better than always answering "fail" (75% of the
  labels are fail), and judge-check now says so in a warning. Every miss went the same
  way: the judge passed a reply the labels failed. Both qwen judges passed case-018
  (llama-13b answered "Here is an allegorical poem that illustrates the above:" and
  no poem) and case-019 (alpaca-13b's rewrite in which most sentences do not start with
  "A").
- The labels came out 18 fail to 6 pass even though `label` split the picks 12/12 by
  the judges' consensus: the judges said pass far more often than the labels did.
- llama3.2:3b changes its verdict on almost half the cases between identical calls.

## DeepEval with the checked judge

`export` wrote `evalset/exports/deepeval/judge.json` (judge `qwen2.5-7b`, its exact
prompt, provider `ollama:chat:qwen2.5:7b-instruct` at temperature 0.8). DeepEval 4.2.8
ran three of the cases on the logged outputs
(`EVAL_BUILDER_USE_OBSERVED=1 pytest test_eval_builder.py -k "case-018 or case-020 or case-040"`):
case-020 passed, case-040 failed with the judge's reason
`{"pass": false, "reason": "Incorrect circumradius calculation."}`, and case-018 (the
missing poem) passed, the same mistake judge-check found.

`evalset/judge_requests.jsonl` (4.7 MB of rendered prompts) is not committed; `judge-plan`
rebuilds it from `cases.yaml` and `rubric.yaml`.
