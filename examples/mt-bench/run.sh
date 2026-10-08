#!/bin/sh
# Reproduce the MT-Bench example end to end from the repository root.
# Needs uv. The judge steps need a local Ollama server with qwen2.5:3b-instruct,
# qwen2.5:7b-instruct, llama3.2:3b and gemma2:2b pulled.
set -e
cd "$(dirname "$0")/../.."

uv run --with pyarrow python examples/mt-bench/prepare.py

# 1. logs -> suite
S=examples/mt-bench/suite
rm -rf "$S"
uv run eval-builder ingest examples/mt-bench/data/logs.jsonl -w "$S"
uv run eval-builder select -w "$S" -n 24 --stratify category
uv run eval-builder draft -w "$S" --suite "MT-Bench conversations as app logs"
uv run python examples/mt-bench/fill_suite.py "$S"      # expected behavior written by the agent
uv run eval-builder validate -w "$S"
uv run eval-builder judge-plan -w "$S" --trials 5 --probes pad --probe-trials 5
uv run eval-builder judge-run -w "$S" --enable-judge-plugin \
  --command "qwen2.5-7b-pointwise=python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct"
uv run eval-builder judge-check -w "$S"
uv run eval-builder export -w "$S"
uv run eval-builder report -w "$S" --title "MT-Bench logs to eval suite"

# 2. judge check against human expert verdicts (pairwise)
J=examples/mt-bench/judges
cp examples/mt-bench/data/pairs_cases.yaml "$J/cases.yaml"
cp examples/mt-bench/data/pairs_labels.jsonl "$J/labels.jsonl"
rm -f "$J/judgments.jsonl"
uv run eval-builder validate -w "$J"
uv run eval-builder judge-plan -w "$J" --trials 5 --probes swap,pad --probe-trials 5
uv run eval-builder judge-run -w "$J" --enable-judge-plugin --timeout 300 \
  --command "control-longer-answer=python examples/judges/control_judges.py --kind longer" \
  --command "control-coin-flip=python examples/judges/control_judges.py --kind coin" \
  --command "qwen2.5-3b=python examples/judges/ollama_judge.py --model qwen2.5:3b-instruct" \
  --command "llama3.2-3b=python examples/judges/ollama_judge.py --model llama3.2:3b" \
  --command "gemma2-2b=python examples/judges/ollama_judge.py --model gemma2:2b --num-ctx 4096" \
  --command "qwen2.5-7b=python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-ctx 4096" \
  --command "qwen2.5-7b-temp0=python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-ctx 4096 --temperature 0"
uv run eval-builder judge-check -w "$J"
uv run eval-builder report -w "$J" --title "MT-Bench judge check"
