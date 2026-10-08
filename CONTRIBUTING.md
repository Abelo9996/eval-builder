# Contributing

Thanks for helping. Before opening a pull request:

1. `uv sync`
2. `uv run pytest -q` (offline, under a minute)
3. `uv run ruff check . && uv run ruff format --check . && uv run mypy src`

New log formats need a small fixture in `tests/fixtures/` and a test. Changes to the
judge statistics need a test against a hand-computed value. See `AGENTS.md` for the
layout and the rules (no model calls, deterministic output, no em dashes in text).
