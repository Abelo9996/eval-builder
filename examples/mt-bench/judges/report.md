# MT-Bench judge check

Generated 2026-10-08T12:10:04+00:00 by eval-builder 0.1.0.

## Cases

80 cases: 80 ready, 0 draft, 0 dropped.

## Judge reliability

Thresholds: flip rate <= 20% (cases with >= 3 trials, >= 10 cases), position consistency >= 80%, padding moves verdict toward padded answer <= 10%, Cohen's kappa >= 0.4 on >= 20 human-labeled cases. Intervals are 95% (Wilson for rates, Cohen's large-sample SE for kappa). Self-agreement is the chance one call matches the judge's own majority; majority-of-3 stable is the chance a 3-call majority vote matches it (exact, needs >= 5 trials).

| judge | mode | verdict | flip rate | self-agreement | majority-of-3 stable | accuracy vs humans | kappa | position consistency | first-shown picked | padding helped |
|---|---|---|---|---|---|---|---|---|---|---|
| control-coin-flip | pairwise | **unstable** | 95% [88%, 98%] (n=80) | 67% | 79% | 51% [40%, 62%] (n=80) | 0.03 [-0.19, 0.24] | 55% [44%, 65%] (n=80) | 50% [47%, 54%] (n=800) | 25% [17%, 35%] (n=80) |
| control-longer-answer | pairwise | **biased** | 0% [0%, 5%] (n=80) | 100% | 100% | 66% [55%, 76%] (n=80) | 0.32 [0.12, 0.53] | 100% [95%, 100%] (n=80) | 50% [47%, 53%] (n=800) | 30% [21%, 41%] (n=80) |
| gemma2-2b | pairwise | **unstable** | 59% [48%, 69%] (n=80) | 82% | 91% | 56% [45%, 67%] (n=80) | 0.14 [-0.07, 0.36] | 38% [28%, 48%] (n=80) | 35% [31%, 38%] (n=798) | 11% [6%, 20%] (n=80) |
| llama3.2-3b | pairwise | **unstable** | 56% [45%, 67%] (n=80) | 82% | 90% | 51% [40%, 62%] (n=80) | 0.04 [-0.17, 0.26] | 14% [8%, 23%] (n=80) | 20% [17%, 22%] (n=800) | 10% [5%, 19%] (n=80) |
| qwen2.5-3b | pairwise | **biased** | 12% [7%, 22%] (n=80) | 95% | 97% | 56% [45%, 67%] (n=80) | 0.13 [-0.08, 0.35] | 44% [33%, 55%] (n=80) | 35% [32%, 38%] (n=800) | 9% [4%, 17%] (n=80) |
| qwen2.5-7b | pairwise | **biased** | 12% [7%, 22%] (n=80) | 96% | 97% | 70% [59%, 79%] (n=80) | 0.40 [0.20, 0.60] | 75% [65%, 83%] (n=80) | 42% [39%, 46%] (n=800) | 1% [0%, 7%] (n=80) |
| qwen2.5-7b-temp0 | pairwise | **biased** | 0% [0%, 5%] (n=80) | 100% | 100% | 72% [62%, 81%] (n=80) | 0.45 [0.26, 0.65] | 75% [65%, 83%] (n=80) | 44% [40%, 47%] (n=800) | 0% [0%, 5%] (n=80) |

- **control-coin-flip** (unstable): verdict changed across repeated trials on 95% of cases (limit 20%). verdict survived swapping answer order on only 55% of cases (need 80%); first-shown answer picked 50% of the time. irrelevant padding moved the verdict toward the padded answer on 25% of cases (limit 10%). agreement with human labels is low: kappa 0.03 (need 0.4), accuracy 51%.
- **control-longer-answer** (biased): irrelevant padding moved the verdict toward the padded answer on 30% of cases (limit 10%). agreement with human labels is low: kappa 0.32 (need 0.4), accuracy 66%.
- **gemma2-2b** (unstable): verdict changed across repeated trials on 59% of cases (limit 20%). verdict survived swapping answer order on only 38% of cases (need 80%); first-shown answer picked 35% of the time. irrelevant padding moved the verdict toward the padded answer on 11% of cases (limit 10%). agreement with human labels is low: kappa 0.14 (need 0.4), accuracy 56%.
- **llama3.2-3b** (unstable): verdict changed across repeated trials on 56% of cases (limit 20%). verdict survived swapping answer order on only 14% of cases (need 80%); first-shown answer picked 20% of the time. agreement with human labels is low: kappa 0.04 (need 0.4), accuracy 51%.
- **qwen2.5-3b** (biased): verdict survived swapping answer order on only 44% of cases (need 80%); first-shown answer picked 35% of the time. agreement with human labels is low: kappa 0.13 (need 0.4), accuracy 56%.
- **qwen2.5-7b** (biased): verdict survived swapping answer order on only 75% of cases (need 80%); first-shown answer picked 42% of the time.
- **qwen2.5-7b-temp0** (biased): verdict survived swapping answer order on only 75% of cases (need 80%); first-shown answer picked 44% of the time.

Judge calls made through the opt-in judge plugin (`judge-run`):

- run 1, llama3.2-3b: `python examples/judges/ollama_judge.py --model llama3.2:3b`, 609 ok, 0 errors, 749.78 s
- run 1, gemma2-2b: `python examples/judges/ollama_judge.py --model gemma2:2b --num-ctx 4096`, 1200 ok, 0 errors, 1088.41 s
- run 1, qwen2.5-7b: `python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-ctx 4096`, 1200 ok, 0 errors, 1361.34 s
- run 1, qwen2.5-7b-temp0: `python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-ctx 4096 --temperature 0`, 1200 ok, 0 errors, 1022.39 s

## Limits

- Selection is lexical (TF-IDF over the user input). Two inputs that mean the same thing in different words can land in different clusters, and near-duplicate detection only catches close textual matches.
- Redaction is pattern-based (emails, common API key formats, Luhn-valid card numbers, US-style phone numbers, SSN-shaped numbers). Names, addresses and free-form secrets are not detected. Review traces before sharing them.
- eval-builder does not write expected behavior. Cases are only as good as what the agent and user put in cases.yaml.
- Judge verdicts depend on the thresholds shown and on how many cases, trials and human labels were provided. Small samples give wide intervals; read the intervals, not just the point estimates.
- The bias probes cover answer order and irrelevant padding only. They do not detect self-preference, style bias or rubric misreadings.
