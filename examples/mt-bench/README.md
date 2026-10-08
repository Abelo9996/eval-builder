# MT-Bench example

A real, small run of eval-builder on public data. Everything here was produced by the
commands in [`run.sh`](run.sh) on an Apple M4 MacBook (16 GB), October 2026.

## Data

[lmsys/mt_bench_human_judgments](https://huggingface.co/datasets/lmsys/mt_bench_human_judgments),
license CC BY 4.0, from Zheng et al. 2023, "Judging LLM-as-a-Judge with MT-Bench and
Chatbot Arena". [`prepare.py`](prepare.py) downloads the `human` split at revision
`f7d2896d2cc5d80f8b55c2bbc722613555233c25` and checks its sha256
(`4877bc46...5769`). It has 3,355 expert pairwise verdicts over answers from six models
(GPT-4, GPT-3.5-turbo, Claude-v1, Vicuna-13B, Alpaca-13B, LLaMA-13B) to 80 two-turn
questions.

`prepare.py` derives two things from it (into `data/`, not committed):

- `logs.jsonl`: the 480 conversations (80 questions x 6 models) in OpenAI chat format,
  as if they were an app's logs, with metadata `category`, `model` and
  `user_feedback`. The feedback is a stand-in for thumbs up/down: `negative` when the
  answer lost every human comparison it was in (at least 3), `positive` when it won
  every one (at least 3). That gives 67 negative, 37 positive, 376 none.
- 80 pairwise judge cases (turn 1, 10 per category, seed 0) where the human verdict
  was not a tie, with that verdict as the label (41 A, 39 B).

Dataset text is kept verbatim, including the model answers' own punctuation.

[`../sample_logs.jsonl`](../sample_logs.jsonl), used by the README quickstart, is a
48-line slice of `logs.jsonl`: the first two questions of each category (81, 82, 91, 92,
..., 151, 152) as answered by gpt-4, alpaca-13b and llama-13b, in file order
(sha256 `2d5dd229...b42b76e`).

## 1. Logs to suite ([`suite/`](suite/))

```
eval-builder ingest data/logs.jsonl -w suite
eval-builder select -w suite -n 24 --stratify category
eval-builder draft -w suite
```

480 traces became 80 unique conversations (400 exact duplicates: each question was
asked to six models; the representative kept is a failing answer when one exists).
Selection picked 24 across 9 topic clusters and all 8 categories, 19 of them failures.
Every pick and its reason is in [`suite/report.md`](suite/report.md).

The expected behavior for each case is in
[`expected_behaviors.yaml`](expected_behaviors.yaml). It was written by Claude Code
acting as the host agent, with the arithmetic checked by script where it could be
(for example the word counts in case-015). No human reviewed it.
[`fill_suite.py`](fill_suite.py) applies it through the same `update_case` and
`set_rubric` calls the MCP server exposes.

Exports in [`suite/exports/`](suite/exports/) were loaded by the real tools
([`verify_exports.sh`](verify_exports.sh)):

- Inspect AI 0.3.277: `json_dataset` loads 24 samples, multi-turn cases as
  user/assistant/user message lists; `inspect eval task.py --model mockllm/model
  --limit 5` runs to completion (the mock model cannot grade, so accuracy is nan).
- DeepEval 4.2.8: `pytest --collect-only` collects 24 tests;
  `add_goldens_from_json_file` loads 24 goldens.
- promptfoo 0.124.0: `promptfoo validate` prints "Configuration is valid."

A pointwise pass/fail judge (`qwen2.5-7b-pointwise` in
[`suite/rubric.yaml`](suite/rubric.yaml), qwen2.5:7b-instruct at temperature 0.8) ran
5 times per case plus 5 times with the reply padded: 240 calls, 0 errors, 192 s. Its
verdict changed across identical calls on 7 of 24 cases (flip rate 29%, 95% interval
15% to 49%), so judge-check marks it `unstable`. Padding never moved a verdict toward
pass (0 of 24). There are no human labels for these cases, so even a stable result
would have been `not_enough_data`.

## 2. Judge check against human experts ([`judges/`](judges/))

Seven pairwise judges (five configurations of four local LLMs, and two controls), each run 5 times per case at its default sampling (seed =
trial index), plus 5 runs with the answers swapped and 5 runs with an irrelevant
paragraph appended to one answer (alternating A and B by case). 80 cases, 1,200 calls
per judge.

Real LLM judges, all local through Ollama 0.30.10, temperature 0.8 unless noted, prompt adapted
from the MT-Bench pairwise judge prompt (see [`judges/rubric.yaml`](judges/rubric.yaml)):

| judge id | Ollama model | size | quantization | context |
|---|---|---|---|---|
| qwen2.5-3b | qwen2.5:3b-instruct (357c53fb659c) | 3.1B | Q4_K_M | 8192 |
| llama3.2-3b | llama3.2:3b (a80c4f17acd5) | 3.2B | Q4_K_M | 8192 |
| gemma2-2b | gemma2:2b (8ccf136fdd52) | 2.6B | Q4_0 | 4096 |
| qwen2.5-7b | qwen2.5:7b-instruct (845dbda0ea48) | 7.6B | Q4_K_M | 4096 |
| qwen2.5-7b-temp0 | same model, temperature 0 | 7.6B | Q4_K_M | 4096 |

The longest prompt any judge received was 1,797 tokens (recorded per call as
`prompt_tokens` in `judgments.jsonl`), so no prompt was truncated.

Controls, which are **not language models** ([`../judges/control_judges.py`](../judges/control_judges.py)):

- `control-longer-answer` picks the longer answer, deterministically.
- `control-coin-flip` picks A or B at random (seeded by request id).

They are there to show that the checks separate noise (coin flip) and a stable but
biased rule (longer answer) from real judges.

### Results

From [`judges/report.md`](judges/report.md). n = 80 pairs per judge, brackets are 95%
intervals (Wilson for rates, Cohen's large-sample standard error for kappa).

| judge | verdict | flip rate | accuracy vs humans | kappa | survives answer swap | first-shown picked | padding helped |
|---|---|---|---|---|---|---|---|
| qwen2.5-7b-temp0 | biased | 0% [0%, 5%] | 72% [62%, 81%] | 0.45 [0.26, 0.65] | 75% [65%, 83%] | 44% [40%, 47%] | 0% [0%, 5%] |
| qwen2.5-7b | biased | 12% [7%, 22%] | 70% [59%, 79%] | 0.40 [0.20, 0.60] | 75% [65%, 83%] | 42% [39%, 46%] | 1% [0%, 7%] |
| qwen2.5-3b | biased | 12% [7%, 22%] | 56% [45%, 67%] | 0.13 [-0.08, 0.35] | 44% [33%, 55%] | 35% [32%, 38%] | 9% [4%, 17%] |
| gemma2-2b | unstable | 59% [48%, 69%] | 56% [45%, 67%] | 0.14 [-0.07, 0.36] | 38% [28%, 48%] | 35% [31%, 38%] | 11% [6%, 20%] |
| llama3.2-3b | unstable | 56% [45%, 67%] | 51% [40%, 62%] | 0.04 [-0.17, 0.26] | 14% [8%, 23%] | 20% [17%, 22%] | 10% [5%, 19%] |
| control-longer-answer | biased | 0% [0%, 5%] | 66% [55%, 76%] | 0.32 [0.12, 0.53] | 100% [95%, 100%] | 50% [47%, 53%] | 30% [21%, 41%] |
| control-coin-flip | unstable | 95% [88%, 98%] | 51% [40%, 62%] | 0.03 [-0.19, 0.24] | 55% [44%, 65%] | 50% [47%, 54%] | 25% [17%, 35%] |

"Survives answer swap" is the share of pairs whose majority verdict is the same after
the two answers trade places. "First-shown picked" counts every A/B verdict in the
original and swapped runs (800 per judge; gemma2-2b gave 2 unparseable answers).

What the numbers say, without extrapolating beyond these 80 pairs:

- No judge passed the default thresholds.
- qwen2.5 7B agrees with the human experts most (kappa 0.40 at temperature 0.8,
  0.45 at temperature 0). Both settings keep their verdict on only 75% of pairs when
  the answers are swapped, just under the 80% threshold. Temperature 0 removed the
  run-to-run flips (12% to 0%) but not the order effect.
- The 2B and 3B models mostly prefer the second answer shown (first-shown picked 20%
  to 35%), and their agreement with the experts is close to chance.
- The longer-answer control never flips and agrees with the experts on 66% of pairs.
  Only the padding probe exposes it (30% of padded pairs moved toward the padded
  answer).
- The coin flip lands where it should: 95% flip rate, kappa 0.03.

The judge run was started once and resumed once (the machine was shared with other
heavy jobs, so the remaining judges were restarted with a smaller context window to
save memory); `judge-run` skips requests that already have a verdict.
`judges/judge_run_log.json` has the resumed run.
