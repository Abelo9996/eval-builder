"""Example judge plugin for `eval-builder judge-run`: a local model served by Ollama.

This is an example, not part of the eval-builder package. It talks only to the
Ollama server on localhost. Protocol: read one JSON request per line on stdin,
write one JSON response per line on stdout: {"verdict": ..., "raw": ...}.

Usage:
  eval-builder judge-run --enable-judge-plugin \\
    --command "qwen-3b=python examples/judges/ollama_judge.py --model qwen2.5:3b-instruct"

Each trial uses seed = trial index, so a rerun on the same machine, model digest and
Ollama version reproduces the same outputs.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def generate(
    host: str,
    model: str,
    prompt: str,
    temperature: float,
    seed: int,
    num_ctx: int,
    num_predict: int,
) -> dict:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "seed": seed,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
    ).encode()
    req = urllib.request.Request(f"{host}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=8)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    args = ap.parse_args()
    for line in sys.stdin:
        req = json.loads(line)
        if not req.get("prompt"):
            print(
                json.dumps({"verdict": None, "raw": "request has no rendered prompt"}), flush=True
            )
            continue
        out = generate(
            args.host,
            args.model,
            req["prompt"],
            args.temperature,
            int(req.get("trial", 0)),
            args.num_ctx,
            args.num_predict,
        )
        text = out.get("response", "")
        print(
            json.dumps(
                {
                    "verdict": text.strip(),
                    "raw": text,
                    "prompt_tokens": out.get("prompt_eval_count"),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
