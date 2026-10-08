# eval-builder

Your agent turns your app's real logs into an eval suite, and tells you which of its judges you can actually trust.

Try it on 48 sample conversations (no account, no API key, no model needed for these steps):

```sh
curl -sLO https://raw.githubusercontent.com/Abelo9996/eval-builder/main/examples/sample_logs.jsonl
uvx eval-builder ingest sample_logs.jsonl     # or your own logs: OpenAI, Anthropic, Langfuse, OpenTelemetry, JSONL
uvx eval-builder select -n 10 --stratify category && uvx eval-builder draft
```

![The quickstart running against eval-builder 0.1.1 from PyPI](docs/demo.gif)

What you get (real output of the commands above, eval-builder 0.1.1 from PyPI; the
curl and the three uvx calls took 35 s in total here; the very first uvx run also
downloads about 38 MiB, mostly numpy, scipy and scikit-learn, which took 6 s here):

```
ingested 48 traces into evalset/traces.jsonl
  sample_logs.jsonl: format=openai records=48 traces=48 skipped=0 sha256=2d5dd2295784988b
redactions: 0 {}
next: eval-builder select -n 30 (add --stratify <metadata keys> to cover them)
48 traces -> 16 unique (32 exact dupes, 0 near dupes) -> selected 10 (8 failures) across 4 clusters
  q121-llama-13b: failure (negative user feedback); 69% of unique traces are failures and at least 30% of picks are reserved for them
  q81-alpaca-13b: failure (negative user feedback); 69% of unique traces are failures and at least 30% of picks are reserved for them
  q102-alpaca-13b: covers category=reasoning (2 unique traces, 12%)
  q111-alpaca-13b: adds variety within cluster 1 (8 traces, 50%; triangle, response, person); least similar to cases already picked there
  ... (6 more picks)
next: run draft to turn the selection into cases.yaml
10 case(s) added, 10 total in evalset/cases.yaml
next: read the cases (list_cases, or cases.yaml), define criteria and judges (set_rubric, or rubric.yaml), fill expected_behavior and criteria per case and set status: ready (update_case), then run validate
```

`evalset/cases.yaml` now holds 10 real conversations with a TODO where the expected
behavior goes. Writing that, running judges and reading the statistics is the part your
coding agent does, through the MCP server (next section).

eval-builder is not another eval platform. It builds the suite and checks the judges,
then exports to the tools you already run: promptfoo, DeepEval, Inspect AI, or plain
JSONL. It never calls a model. Your coding agent (Claude Code, Codex, Cursor) does the
thinking; eval-builder does the selection, the bookkeeping and the statistics, and
writes down the evidence.

## Use it with your agent

```sh
uvx eval-builder setup --yes    # registers the MCP server and the skill, then restart your agent
```

Then type something like this into Claude Code, from the folder that has your logs:

> Our assistant's chat logs from last month are in ./logs. Build a small eval suite from
> them (about 10 cases) that I can run in promptfoo, and tell me whether I can trust a
> local judge for grading it. I have Ollama running with qwen2.5:7b-instruct and
> llama3.2:3b. Keep the judge runs small.

This is from a real headless Claude Code session (October 2026, Claude Code 2.1.293)
given exactly that prompt and 48 conversations from [`examples/sample_logs.jsonl`](examples/sample_logs.jsonl).
It ran ingest, select, draft, list_cases, set_rubric, ten update_case calls, validate,
judge_plan, 140 judge calls to Ollama through a short script it wrote, judge_check,
export and report in 32 turns and about 10 minutes. From its final answer:

> I built a 10-case promptfoo suite, but **you can't trust either local judge yet.**
> Neither one has been checked against human labels, and each confidently got an
> obvious case wrong.
>
> | judge | flip rate | padding helped | verdict |
> |---|---|---|---|
> | qwen2.5:7b-instruct | 10% [2%, 40%] (n=10) | 0% [0%, 28%] | not_enough_data |
> | llama3.2:3b | 20% [6%, 51%] (n=10) | 0% [0%, 28%] | not_enough_data |
>
> **qwen7b failed a clear case.** It passed the Hawaii rewrite 5 out of 5 times, though
> only the first sentence starts with "A".
>
> **No grader is wired in.** Because no judge passed, the `llm-rubric` checks fall back to
> promptfoo's default grader, which needs an OpenAI key. To grade locally anyway, export
> again with the judge set explicitly (the `export` tool's `judge` option, e.g. `qwen7b`).
> Its verdicts will be unverified.

It wrote every expected behavior itself because nobody was there to confirm them, and
said so on each case. It did not invent human labels; it asked for them.

An earlier session against 0.1.0 is where the promptfoo context bug fixed in 0.1.1 came
from. The agent read the export and told the user: "Right now it only sends the final
question (`{{input}}`), so your app won't see what "it" refers to in "Can you
parallelize it?"."

## Example: real output

Everything below comes from runs on this machine (Apple M4, 16 GB) that are committed
in [`examples/mt-bench/`](examples/mt-bench/). The data is the LMSYS
[MT-Bench human judgments](https://huggingface.co/datasets/lmsys/mt_bench_human_judgments)
dataset (CC BY 4.0): 80 two-turn questions answered by 6 models, plus pairwise verdicts
from expert human judges.

**Logs to suite.** `ingest` read 480 conversations (OpenAI chat format, redaction on,
0 matches). `select -n 24 --stratify category` removed 400 exact duplicates (each
question was asked to six models), clustered the 80 unique conversations into 9 topics
and picked 24 covering all 8 categories, 19 of them failures. From
[`suite/report.md`](examples/mt-bench/suite/report.md):

```
| trace           | cluster | represents | why it was picked |
| q81-alpaca-13b  | 0 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| q82-alpaca-13b  | 0 | 6 | adds variety within cluster 0 (11 traces, 14%; response, previous response, previous); least similar to cases already picked there |
| q156-alpaca-13b | 3 | 6 | covers category=humanities (10 unique traces, 12%) |
```

The agent wrote expected behavior for the 24 cases, and `export` produced files that
Inspect AI 0.3.277, DeepEval 4.2.8 and promptfoo 0.124.0 all load (see
[`verify_exports.sh`](examples/mt-bench/verify_exports.sh)).

**Which judges can you trust?** Five local LLM judge setups (four models through
Ollama, one of them also at temperature 0) and two controls that are not language models judged 80 answer pairs where human experts
picked a winner. Each judge ran 5 times per pair, 5 more with the answers swapped, and
5 more with an irrelevant paragraph appended to one answer: 8,400 calls, 0 errors.
`eval-builder judge-check`, from [`judges/report.md`](examples/mt-bench/judges/report.md):

| judge | verdict | flip rate | accuracy vs humans | kappa | survives answer swap | first-shown answer picked | padding helped |
|---|---|---|---|---|---|---|---|
| qwen2.5:7b-instruct, temp 0 | biased | 0% [0%, 5%] | 72% [62%, 81%] | 0.45 [0.26, 0.65] | 75% [65%, 83%] | 44% | 0% |
| qwen2.5:7b-instruct, temp 0.8 | biased | 12% [7%, 22%] | 70% [59%, 79%] | 0.40 [0.20, 0.60] | 75% [65%, 83%] | 42% | 1% |
| qwen2.5:3b-instruct | biased | 12% [7%, 22%] | 56% [45%, 67%] | 0.13 [-0.08, 0.35] | 44% [33%, 55%] | 35% | 9% |
| gemma2:2b | unstable | 59% [48%, 69%] | 56% [45%, 67%] | 0.14 [-0.07, 0.36] | 38% [28%, 48%] | 35% | 11% |
| llama3.2:3b | unstable | 56% [45%, 67%] | 51% [40%, 62%] | 0.04 [-0.17, 0.26] | 14% [8%, 23%] | 20% | 10% |
| control: longer answer wins | biased | 0% [0%, 5%] | 66% [55%, 76%] | 0.32 [0.12, 0.53] | 100% [95%, 100%] | 50% | 30% |
| control: coin flip | unstable | 95% [88%, 98%] | 51% [40%, 62%] | 0.03 [-0.19, 0.24] | 55% [44%, 65%] | 50% | 25% |

n = 80 pairs per judge; brackets are 95% intervals. No judge passed. The closest,
qwen2.5 7B, reaches kappa 0.40 to 0.45 with the human experts, but its verdict
flips on a quarter of the pairs when the answer order is swapped, and setting the
temperature to 0 removes the run-to-run flips without removing that order effect.
llama3.2 3B picked whichever answer it saw second 80% of the time. The longer-answer
rule never flips and agrees with humans 66% of the time, which is why stability and
accuracy alone are not enough: the padding probe catches it.

The same check on the suite's own pass/fail judge (qwen2.5 7B, 24 cases, no human
labels) gives `unstable`: its verdict changed across 5 identical calls on 7 of 24
cases (29%, interval 15% to 49%).

## How it works

| step | what it does | what it uses |
|---|---|---|
| `ingest` | Reads OpenAI chat JSONL (fine-tuning style or request/response logs), Anthropic messages, Langfuse trace exports, OpenTelemetry GenAI spans (OTLP JSON, current `gen_ai.input.messages` and older `gen_ai.prompt.N` attributes), or generic input/output JSONL. Normalizes to one schema with input, output, earlier turns, tools called, error flag, user feedback, route and model. Redacts emails, API keys, Luhn-valid card numbers, phone numbers and SSN-shaped numbers by default and reports counts. | Python standard library |
| `select` | Removes exact duplicates (normalized hash of the user turns) and near-duplicates (character n-gram cosine), clusters the rest by topic, then picks: failures first (errors, negative feedback), at least one case per stratum (route, tool, feedback, any metadata key you name), one central case per cluster, and fills the rest by cluster size with the least similar remaining cases. Every pick records why it was picked. | scikit-learn (TF-IDF, k-means) |
| `draft`, `validate` | Writes `cases.yaml` and `rubric.yaml` with TODO markers. The agent fills in expected behavior and criteria with you. Validation refuses ready cases that still contain TODO or reference unknown criteria. | PyYAML |
| `judge-plan` | Lists every judge call to make: each case N times, plus probes that swap the answer order (pairwise judges) and pad an answer with an irrelevant paragraph. | |
| `judge-run` | Optional and off by default. Sends each request as a JSON line to a command you name (your script, your provider, your keys) and records the verdicts. eval-builder ships no API keys and no provider code. | your command |
| `judge-check` | Per judge: flip rate across repeated calls (with a Wilson interval), self-agreement, majority-of-3 vote stability, accuracy and Cohen's kappa against your human labels (with intervals), position consistency and first-shown preference, and how often padding moved the verdict toward the padded answer. Verdict: `trustworthy`, `unstable`, `biased`, `misaligned`, or `not_enough_data`, with the numbers behind it. | |
| `export` | promptfoo `promptfooconfig.yaml` (the full conversation as chat messages, llm-rubric asserts, and a judge that passed judge-check wired in as the grader when its rubric entry names a promptfoo `provider`), DeepEval dataset plus a `deepeval test run` file, Inspect AI dataset plus `task.py`, plain JSONL. The manifest lists file hashes and which judges passed. | |
| `report` | `report.md` and `report.json`: sources with sha256, counts, redactions, selection reasons, the judge table, and the limits. | |

The verdict thresholds are explicit flags with defaults: flip rate at most 20% of cases,
position consistency at least 80%, padding helps at most 10% of cases, kappa at least
0.4 on at least 20 human-labeled cases. A judge without human labels is never called
trustworthy.

## Setup for agents

```sh
uvx eval-builder setup          # shows what it would change
uvx eval-builder setup --yes    # applies it; restart your agent afterwards
```

`setup` registers the MCP server (`uvx eval-builder mcp`) with Claude Code (`claude mcp
add --scope user`), Codex (`[mcp_servers.eval-builder]` in `~/.codex/config.toml`) and
Cursor (`~/.cursor/mcp.json`), and copies the agent instructions to
`~/.claude/skills/eval-builder/` and `~/.codex/skills/eval-builder/`. It backs up any
file it edits and does nothing on a second run. The workflow the agent follows is in
[`skills/eval-builder/SKILL.md`](skills/eval-builder/SKILL.md).

MCP tools: `ingest`, `select`, `draft`, `list_cases`, `update_case`, `set_rubric`,
`validate`, `judge_plan`, `judge_check`, `export`, `report`, `status`. The judge runner
is CLI only, because it executes a command.

## What it can't do

- It does not write expected behavior or human labels. The agent drafts expected
  behavior with you; labels must come from people. Without labels, judge-check can
  tell you a judge is unstable or biased, but not that it is right.
- Selection is lexical. Two requests that mean the same thing in different words can
  land in different clusters, and near-duplicate detection only catches close textual
  matches.
- Redaction is pattern-based. Names, street addresses and free-form secrets get
  through. Look at `traces.jsonl` before sharing a workspace.
- The bias probes cover answer order and irrelevant length only. Self-preference,
  style bias and rubric misreadings are not measured.
- Small samples give wide intervals. The report prints them; read them.
- It does not run your app, your judges or your eval. The agent (or a script you name
  with `judge-run`) calls the judge model; the exported files run the eval in promptfoo,
  DeepEval or Inspect AI.
- Only the promptfoo export wires a checked judge in as the grader, and only a
  pointwise judge whose prompt answers in JSON (`{"pass": ..., "reason": ...}`), because
  promptfoo's llm-rubric cannot parse a bare "pass". DeepEval and Inspect exports use
  their own default graders.

## Privacy and safety

Everything runs locally. eval-builder makes no network calls and sends nothing
anywhere. The only process it starts is the judge command you name with
`judge-run --enable-judge-plugin`. Redaction is on unless you pass `--no-redact`, and
the report lists what was replaced (counts and kinds, never the values).

## License

MIT. See [LICENSE](LICENSE).
