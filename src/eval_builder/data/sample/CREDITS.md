# Bundled sample: MT-Bench human judgments

`mt_bench_pairs.jsonl` is a redistributed subset of the LMSYS
[MT-Bench human judgments](https://huggingface.co/datasets/lmsys/mt_bench_human_judgments)
dataset (license **CC BY 4.0**), from Zheng et al. 2023, "Judging LLM-as-a-Judge with
MT-Bench and Chatbot Arena".

It holds 80 turn-1 pairwise comparisons (10 per MT-Bench category) between answers from
six models (GPT-4, GPT-3.5-turbo, Claude-v1, Vicuna-13B, Alpaca-13B, LLaMA-13B), each
with the winner chosen by expert human judges (41 A, 39 B; ties dropped). Dataset text
is kept verbatim.

`judge-check` uses these pairs with no labels needed for its bias and stability probes,
and uses `human_label` to also report agreement with the human experts.

The full download, pinned revision and sha256, and the code that derived these pairs
are in [`examples/mt-bench/prepare.py`](../../../../examples/mt-bench/prepare.py).
