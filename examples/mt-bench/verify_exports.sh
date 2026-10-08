#!/bin/sh
# Load the exported suite with the real tools. Nothing here calls a model provider:
# Inspect runs against its offline mock model, DeepEval only collects the tests, and
# promptfoo only validates the config. Caches go to /tmp.
set -e
E="$(cd "$(dirname "$0")" && pwd)/suite/exports"

echo "== Inspect AI"
(cd "$E/inspect" && uv run --no-project --with inspect-ai inspect eval task.py \
  --model mockllm/model --limit 5 --log-dir /tmp/eval-builder-inspect-logs)

echo "== DeepEval"
(cd "$E/deepeval" && OPENAI_API_KEY=not-used uv run --no-project --with deepeval --with pytest \
  python -m pytest --collect-only -q -p no:cacheprovider test_eval_builder.py)

echo "== promptfoo"
(cd "$E/promptfoo" && npm_config_cache=/tmp/eval-builder-npm PROMPTFOO_DISABLE_TELEMETRY=1 \
  PROMPTFOO_CONFIG_DIR=/tmp/eval-builder-promptfoo npx -y promptfoo@latest validate \
  -c promptfooconfig.yaml)
