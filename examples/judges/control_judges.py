"""Control judges for `eval-builder judge-run`. These are NOT language models.

  --kind longer   picks whichever answer is longer (a deterministic heuristic)
  --kind coin     picks A or B at random (seeded by request id), a pure-noise control

They exist to show that judge-check separates "stable but biased" (longer) and
"noise" (coin) from real judges. Never report them as LLM judges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["longer", "coin"], required=True)
    args = ap.parse_args()
    for line in sys.stdin:
        req = json.loads(line)
        shown = req["presented"]
        if args.kind == "longer":
            verdict = "A" if len(shown["answer_a"]) >= len(shown["answer_b"]) else "B"
        else:
            h = hashlib.sha256(req["request_id"].encode()).digest()[0]
            verdict = "A" if h % 2 == 0 else "B"
        print(json.dumps({"verdict": verdict}), flush=True)


if __name__ == "__main__":
    main()
