# Labeling example on the 48-conversation sample

Generated 2026-10-09T08:21:43+00:00 by eval-builder 0.1.2.

## Sources

| file | format | sha256 | records | traces | skipped |
|---|---|---|---|---|---|
| sample_logs.jsonl | openai | `2d5dd2295784988b` | 48 | 48 | 0 |

Traces ingested: 48 (48 multi-turn, 0 with an error flag). Feedback: negative 13, positive 2, none 33.

## Redactions

Redaction was on. No matches.

## Selection

48 traces, 0 exact duplicates removed, 1 near-duplicates merged (cosine >= 0.99 on the user turns plus the output), 47 unique. Selected 47 (13 failures; failures are 13 of 47 unique traces). Seed 0, 7 k-means clusters.

| cluster | traces | share | selected | top terms |
|---|---|---|---|---|
| 0 | 9 | 19% | 9 | like, elon, elon musk, musk, indicators |
| 1 | 9 | 19% | 9 | number, write, program, program nth, write program |
| 2 | 9 | 19% | 9 | response, email, point, post, sentence |
| 3 | 8 | 17% | 8 | person, house, second, second person, just |
| 4 | 3 | 6% | 3 | movie, released, parts, json, movie released |
| 5 | 3 | 6% | 3 | triangle, area, triangle area, area circle, area triangle |
| 6 | 6 | 13% | 6 | quantum, satellite, physics, cases, assumptions response |

| stratum | value | unique traces | selected |
|---|---|---|---|
| feedback | (none) | 32 | 32 |
| feedback | negative | 13 | 13 |
| feedback | positive | 2 | 2 |
| category | coding | 6 | 6 |
| category | extraction | 6 | 6 |
| category | humanities | 6 | 6 |
| category | math | 5 | 5 |
| category | reasoning | 6 | 6 |
| category | roleplay | 6 | 6 |
| category | stem | 6 | 6 |
| category | writing | 6 | 6 |
| model | alpaca-13b | 16 | 16 |
| model | gpt-4 | 16 | 16 |
| model | llama-13b | 15 | 15 |

| trace | cluster | represents | why it was picked |
|---|---|---|---|
| `q91-alpaca-13b` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q91-gpt-4` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q91-llama-13b` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q92-alpaca-13b` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q92-gpt-4` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q92-llama-13b` | 0 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q151-alpaca-13b` | 0 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q151-gpt-4` | 0 | 1 | adds variety within cluster 0 (9 traces, 19%; like, elon, elon musk); least similar to cases already picked there |
| `q151-llama-13b` | 0 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q121-alpaca-13b` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q121-gpt-4` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q121-llama-13b` | 1 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q122-alpaca-13b` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q122-gpt-4` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q122-llama-13b` | 1 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q152-alpaca-13b` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q152-gpt-4` | 1 | 1 | adds variety within cluster 1 (9 traces, 19%; number, write, program); least similar to cases already picked there |
| `q152-llama-13b` | 1 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q81-alpaca-13b` | 2 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q81-gpt-4` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q81-llama-13b` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q82-alpaca-13b` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q82-gpt-4` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q82-llama-13b` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q132-alpaca-13b` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q132-gpt-4` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q132-llama-13b` | 2 | 1 | adds variety within cluster 2 (9 traces, 19%; response, email, point); least similar to cases already picked there |
| `q101-alpaca-13b` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q101-gpt-4` | 3 | 1 | covers feedback=positive (2 unique traces, 4%) |
| `q101-llama-13b` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q102-alpaca-13b` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q102-gpt-4` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q102-llama-13b` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q112-alpaca-13b` | 3 | 2 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q112-gpt-4` | 3 | 1 | adds variety within cluster 3 (8 traces, 17%; person, house, second); least similar to cases already picked there |
| `q131-alpaca-13b` | 4 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q131-gpt-4` | 4 | 1 | adds variety within cluster 4 (3 traces, 6%; movie, released, parts); least similar to cases already picked there |
| `q131-llama-13b` | 4 | 1 | adds variety within cluster 4 (3 traces, 6%; movie, released, parts); least similar to cases already picked there |
| `q111-alpaca-13b` | 5 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q111-gpt-4` | 5 | 1 | covers feedback=(none) (32 unique traces, 68%) |
| `q111-llama-13b` | 5 | 1 | adds variety within cluster 5 (3 traces, 6%; triangle, area, triangle area); least similar to cases already picked there |
| `q141-alpaca-13b` | 6 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q141-gpt-4` | 6 | 1 | adds variety within cluster 6 (6 traces, 13%; quantum, satellite, physics); least similar to cases already picked there |
| `q141-llama-13b` | 6 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |
| `q142-alpaca-13b` | 6 | 1 | adds variety within cluster 6 (6 traces, 13%; quantum, satellite, physics); least similar to cases already picked there |
| `q142-gpt-4` | 6 | 1 | adds variety within cluster 6 (6 traces, 13%; quantum, satellite, physics); least similar to cases already picked there |
| `q142-llama-13b` | 6 | 1 | failure (negative user feedback); 28% of unique traces are failures and at least 30% of picks are reserved for them |

## Cases

47 cases: 47 ready, 0 draft, 0 dropped.

## Judge reliability

Thresholds: flip rate <= 20% (cases with >= 3 trials, >= 10 cases), position consistency >= 80%, padding moves verdict toward padded answer <= 10%, Cohen's kappa >= 0.4 on >= 20 human-labeled cases. Intervals are 95% (Wilson for rates, Cohen's large-sample SE for kappa). Self-agreement is the chance one call matches the judge's own majority; majority-of-3 stable is the chance a 3-call majority vote matches it (exact, needs >= 5 trials).

| judge | mode | verdict | flip rate | self-agreement | majority-of-3 stable | accuracy vs humans | kappa | position consistency | first-shown picked | padding helped |
|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2-3b | pointwise | **unstable** | 47% [33%, 61%] (n=47) | 83% | 88% | 54% [35%, 72%] (n=24) | 0.12 [-0.26, 0.50] | n/a | n/a | 4% [1%, 14%] (n=47) |
| qwen2.5-7b | pointwise | **trustworthy** | 9% [3%, 20%] (n=47) | 97% | 97% | 71% [51%, 85%] (n=24) | 0.44 [0.09, 0.79] | n/a | n/a | 0% [0%, 8%] (n=47) |
| qwen2.5-7b-temp0 | pointwise | **trustworthy** | 0% [0%, 8%] (n=47) | 100% | 100% | 75% [55%, 88%] (n=24) | 0.50 [0.15, 0.85] | n/a | n/a | 0% [0%, 8%] (n=47) |

- **llama3.2-3b** (unstable): verdict changed across repeated trials on 47% of cases (limit 20%). agreement with human labels is low: kappa 0.12 (need 0.4), accuracy 54%.
- **qwen2.5-7b** (trustworthy): stable (flip rate 9%), kappa 0.44 with humans.
- **qwen2.5-7b-temp0** (trustworthy): stable (flip rate 0%), kappa 0.50 with humans.

Human labels on judged cases: fail 18 of 24 (75%), pass 6 (25%). A judge that always gave the most common label would score 75% accuracy, which is the bar accuracy has to clear; kappa already corrects for it.

- Warning: judge llama3.2-3b's accuracy (54%) is no better than always answering 'fail' (75%) on these 24 labeled cases (the judge said pass 13 of 24 (54%), fail 11 (46%)); kappa 0.12 [-0.26, 0.50] is the number that corrects for this. Look at the cases it got wrong before relying on it
- Warning: judge qwen2.5-7b's accuracy (71%) is no better than always answering 'fail' (75%) on these 24 labeled cases (the judge said pass 13 of 24 (54%), fail 11 (46%)); kappa 0.44 [0.09, 0.79] is the number that corrects for this. Look at the cases it got wrong before relying on it
- Warning: judge qwen2.5-7b-temp0's accuracy (75%) is no better than always answering 'fail' (75%) on these 24 labeled cases (the judge said fail 12 of 24 (50%), pass 12 (50%)); kappa 0.50 [0.15, 0.85] is the number that corrects for this. Look at the cases it got wrong before relying on it

Judge calls made through the opt-in judge plugin (`judge-run`):

- run 1, qwen2.5-7b: `python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-predict 80`, 376 ok, 0 errors, 1114.1 s
- run 1, qwen2.5-7b-temp0: `python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-predict 80 --temperature 0`, 376 ok, 0 errors, 1129.93 s
- run 1, llama3.2-3b: `python examples/judges/ollama_judge.py --model llama3.2:3b --num-predict 80`, 376 ok, 0 errors, 589.09 s

## Exports

47 ready cases exported.

| file | sha256 |
|---|---|
| exports/promptfoo/promptfooconfig.yaml | `23c43efb656ee17c` |
| exports/deepeval/dataset.json | `f6cf982eeef58e13` |
| exports/deepeval/test_eval_builder.py | `05f445309c2983af` |
| exports/deepeval/judge.json | `dd632220790c10ab` |
| exports/inspect/dataset.jsonl | `63fb2547e1e81007` |
| exports/inspect/task.py | `df284b6b6dedeb83` |
| exports/jsonl/cases.jsonl | `d10eff47dcc67a11` |

## Limits

- Selection is lexical (TF-IDF over the user input). Two inputs that mean the same thing in different words can land in different clusters, and near-duplicate detection only catches close textual matches.
- Redaction is pattern-based (emails, common API key formats, Luhn-valid card numbers, US-style phone numbers, SSN-shaped numbers). Names, addresses and free-form secrets are not detected. Review traces before sharing them.
- eval-builder does not write expected behavior. Cases are only as good as what the agent and user put in cases.yaml.
- Judge verdicts depend on the thresholds shown and on how many cases, trials and human labels were provided. Small samples give wide intervals; read the intervals, not just the point estimates.
- The bias probes cover answer order and irrelevant padding only. They do not detect self-preference, style bias or rubric misreadings.
