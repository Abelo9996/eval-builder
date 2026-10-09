#!/bin/sh
# Reproduce the labeling example from the repository root. Needs uv, a local Ollama
# server with qwen2.5:7b-instruct and llama3.2:3b pulled, and (for the sheet check)
# Google Chrome. The labels themselves come from a person using label_sheet.html;
# drive_sheet.py replays recorded decisions through the sheet in headless Chrome.
set -e
cd "$(dirname "$0")/../.."
E=examples/sample-labeling/evalset
rm -rf "$E"

# 1. logs -> 47 ready cases (dedupe on input+output keeps each model's answer)
uv run eval-builder ingest examples/sample_logs.jsonl -w "$E"
uv run eval-builder select -w "$E" -n 48 --dedupe-on input+output --near-dup 0.99 \
  --stratify category,model
uv run eval-builder draft -w "$E" --suite "MT-Bench sample, labeling example"
uv run python examples/sample-labeling/fill.py "$E"
uv run eval-builder validate -w "$E"

# 2. three local judges, 5 trials per case plus 3 with the reply padded
uv run eval-builder judge-plan -w "$E" --trials 5 --probes pad --probe-trials 3
uv run eval-builder judge-run -w "$E" --enable-judge-plugin --timeout 300 \
  --command "qwen2.5-7b=python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-predict 80" \
  --command "qwen2.5-7b-temp0=python examples/judges/ollama_judge.py --model qwen2.5:7b-instruct --num-predict 80 --temperature 0" \
  --command "llama3.2-3b=python examples/judges/ollama_judge.py --model llama3.2:3b --num-predict 80"
uv run eval-builder judge-check -w "$E"

# 3. pick 24 cases, label them in the sheet, import, check the judges against the labels
uv run eval-builder label -w "$E"
uv run --no-project --with playwright python examples/sample-labeling/drive_sheet.py \
  "$E/label_sheet.html" examples/sample-labeling/decisions.json examples/sample-labeling/sheet-run \
  --labeler developer
uv run eval-builder label import examples/sample-labeling/sheet-run/labels.jsonl -w "$E"
uv run eval-builder judge-check -w "$E"
uv run eval-builder export -w "$E"
uv run eval-builder report -w "$E" --title "Labeling example on the 48-conversation sample"
