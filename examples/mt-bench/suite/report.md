# MT-Bench logs to eval suite

Generated 2026-10-08T12:13:29+00:00 by eval-builder 0.1.0.

## Sources

| file | format | sha256 | records | traces | skipped |
|---|---|---|---|---|---|
| logs.jsonl | openai | `b718e2880b100ba6` | 480 | 480 | 0 |

Traces ingested: 480 (480 multi-turn, 0 with an error flag). Feedback: negative 67, none 376, positive 37.

## Redactions

Redaction was on. No matches.

## Selection

480 traces, 400 exact duplicates removed, 0 near-duplicates merged (cosine >= 0.9 on the user turns), 80 unique. Selected 24 (19 failures; failures are 50 of 80 unique traces). Seed 0, 9 k-means clusters.

| cluster | traces | share | selected | top terms |
|---|---|---|---|---|
| 0 | 11 | 14% | 3 | response, previous response, previous, sentence, post |
| 1 | 14 | 18% | 4 | 4z, express, triangle, year, total |
| 2 | 7 | 9% | 3 | time, complexity, implement, time complexity, does |
| 3 | 8 | 10% | 3 | learning, use, explain, provide, example |
| 4 | 10 | 12% | 3 | word, like, river, musk, elon musk |
| 5 | 7 | 9% | 2 | tree, binary, binary tree, function, write function |
| 6 | 6 | 8% | 1 | number, 10, program, divided, number divided |
| 7 | 10 | 12% | 3 | question, explain, father, david, brothers |
| 8 | 7 | 9% | 2 | color, green, car, new, business |

| stratum | value | unique traces | selected |
|---|---|---|---|
| feedback | (none) | 30 | 5 |
| feedback | negative | 50 | 19 |
| category | coding | 10 | 4 |
| category | extraction | 10 | 2 |
| category | humanities | 10 | 2 |
| category | math | 10 | 5 |
| category | reasoning | 10 | 3 |
| category | roleplay | 10 | 1 |
| category | stem | 10 | 4 |
| category | writing | 10 | 3 |

| trace | cluster | represents | why it was picked |
|---|---|---|---|
| `q81-alpaca-13b` | 0 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q82-alpaca-13b` | 0 | 6 | adds variety within cluster 0 (11 traces, 14%; response, previous response, previous); least similar to cases already picked there |
| `q144-alpaca-13b` | 0 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q111-alpaca-13b` | 1 | 6 | adds variety within cluster 1 (14 traces, 18%; 4z, express, triangle); least similar to cases already picked there |
| `q116-alpaca-13b` | 1 | 6 | adds variety within cluster 1 (14 traces, 18%; 4z, express, triangle); least similar to cases already picked there |
| `q119-alpaca-13b` | 1 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q134-alpaca-13b` | 1 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q126-alpaca-13b` | 2 | 6 | covers feedback=(none) (30 unique traces, 38%) |
| `q129-llama-13b` | 2 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q130-llama-13b` | 2 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q95-alpaca-13b` | 3 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q146-llama-13b` | 3 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q156-alpaca-13b` | 3 | 6 | covers category=humanities (10 unique traces, 12%) |
| `q87-llama-13b` | 4 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q136-llama-13b` | 4 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q142-llama-13b` | 4 | 6 | adds variety within cluster 4 (10 traces, 12%; word, like, river); least similar to cases already picked there |
| `q125-alpaca-13b` | 5 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q145-alpaca-13b` | 5 | 6 | adds variety within cluster 5 (7 traces, 9%; tree, binary, binary tree); least similar to cases already picked there |
| `q118-alpaca-13b` | 6 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q103-llama-13b` | 7 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q104-vicuna-13b-v1.2` | 7 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q106-gpt-3.5-turbo` | 7 | 6 | adds variety within cluster 7 (10 traces, 12%; question, explain, father); least similar to cases already picked there |
| `q113-alpaca-13b` | 8 | 6 | failure (negative user feedback); 62% of unique traces are failures and at least 30% of picks are reserved for them |
| `q159-alpaca-13b` | 8 | 6 | adds variety within cluster 8 (7 traces, 9%; color, green, car); least similar to cases already picked there |

## Cases

24 cases: 24 ready, 0 draft, 0 dropped.

## Judge reliability

Thresholds: flip rate <= 20% (cases with >= 3 trials, >= 10 cases), position consistency >= 80%, padding moves verdict toward padded answer <= 10%, Cohen's kappa >= 0.4 on >= 20 human-labeled cases. Intervals are 95% (Wilson for rates, Cohen's large-sample SE for kappa). Self-agreement is the chance one call matches the judge's own majority; majority-of-3 stable is the chance a 3-call majority vote matches it (exact, needs >= 5 trials).

| judge | mode | verdict | flip rate | self-agreement | majority-of-3 stable | accuracy vs humans | kappa | position consistency | first-shown picked | padding helped |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-pointwise | pointwise | **unstable** | 29% [15%, 49%] (n=24) | 90% | 94% | n/a | n/a | n/a | n/a | 0% [0%, 14%] (n=24) |

- **qwen2.5-7b-pointwise** (unstable): verdict changed across repeated trials on 29% of cases (limit 20%).

Judge calls made through the opt-in judge plugin (`judge-run`):

- run 1, qwen2.5-7b-pointwise: `python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-ctx 4096`, 240 ok, 0 errors, 191.69 s

## Exports

24 ready cases exported.

| file | sha256 |
|---|---|
| exports/promptfoo/promptfooconfig.yaml | `8cf28fe31810942f` |
| exports/deepeval/dataset.json | `9f8184fa50a284c6` |
| exports/deepeval/test_eval_builder.py | `eaa505fed9db83a8` |
| exports/inspect/dataset.jsonl | `a5549d41878924bd` |
| exports/inspect/task.py | `df284b6b6dedeb83` |
| exports/jsonl/cases.jsonl | `126606d67661e353` |

## Limits

- Selection is lexical (TF-IDF over the user input). Two inputs that mean the same thing in different words can land in different clusters, and near-duplicate detection only catches close textual matches.
- Redaction is pattern-based (emails, common API key formats, Luhn-valid card numbers, US-style phone numbers, SSN-shaped numbers). Names, addresses and free-form secrets are not detected. Review traces before sharing them.
- eval-builder does not write expected behavior. Cases are only as good as what the agent and user put in cases.yaml.
- Judge verdicts depend on the thresholds shown and on how many cases, trials and human labels were provided. Small samples give wide intervals; read the intervals, not just the point estimates.
- The bias probes cover answer order and irrelevant padding only. They do not detect self-preference, style bias or rubric misreadings.
- No human labels were provided, so no judge can be marked trustworthy.
