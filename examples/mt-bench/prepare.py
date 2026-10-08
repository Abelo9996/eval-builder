"""Download MT-Bench human judgments and turn them into app-style logs and judge cases.

Dataset: lmsys/mt_bench_human_judgments (CC BY 4.0), Zheng et al. 2023,
"Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena". Pinned to a revision and
checked by sha256 so the example is reproducible.

Writes (into --out, default ./data, git-ignored):
  logs.jsonl          480 conversations (80 questions x 6 models) in OpenAI chat format
  pairs_cases.yaml    pairwise judge cases (turn 1, human winner not a tie)
  pairs_labels.jsonl  the human expert verdict for each pairwise case

Run with: uv run --with pyarrow python examples/mt-bench/prepare.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import yaml

REPO = "lmsys/mt_bench_human_judgments"
REVISION = "f7d2896d2cc5d80f8b55c2bbc722613555233c25"
FILE = "data/human-00000-of-00001-25f4910818759289.parquet"
SHA256 = "4877bc46a40929f4082c3c79593700fb897b1d6c7f4c473032694a01322f5769"
URL = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{FILE}"

# MT-Bench question ids 81-160 come in blocks of ten per category (FastChat question.jsonl).
CATEGORIES = [
    "writing",
    "roleplay",
    "reasoning",
    "math",
    "coding",
    "extraction",
    "stem",
    "humanities",
]


def category(qid: int) -> str:
    return CATEGORIES[(qid - 81) // 10]


def _feedback(wins: int, losses: int) -> str | None:
    if wins == 0 and losses >= 3:
        return "negative"
    if losses == 0 and wins >= 3:
        return "positive"
    return None


def fetch(dest: Path) -> Path:
    path = dest / "human.parquet"
    if not path.exists():
        dest.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"sha256 mismatch for {path}: {digest}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"))
    ap.add_argument("--pairs", type=int, default=80, help="pairwise cases (10 per category)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    out = Path(args.out)
    rows = pq.read_table(fetch(out)).to_pylist()

    # 1. logs: one conversation per (question, model), the longest version seen (2 turns)
    convs: dict[tuple[int, str], list[dict[str, str]]] = {}
    record: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for r in rows:
        for side in ("a", "b"):
            key = (r["question_id"], r[f"model_{side}"])
            conv = r[f"conversation_{side}"]
            if len(conv) > len(convs.get(key, [])):
                convs[key] = conv
            if r["winner"] == f"model_{side}":
                record[key]["win"] += 1
            elif r["winner"] != "tie":
                record[key]["loss"] += 1
    with open(out / "logs.jsonl", "w", encoding="utf-8") as f:
        for (qid, model), conv in sorted(convs.items()):
            w, lo = record[(qid, model)]["win"], record[(qid, model)]["loss"]
            # Stand-in for thumbs up/down: the answer lost (or won) every human comparison
            # it appeared in, with at least three comparisons.
            feedback = _feedback(w, lo)
            meta = {
                "question_id": qid,
                "category": category(qid),
                "model": model,
                "human_pairwise_wins": w,
                "human_pairwise_losses": lo,
            }
            if feedback:
                meta["user_feedback"] = feedback
            f.write(
                json.dumps(
                    {
                        "id": f"q{qid}-{model}",
                        "model": model,
                        "messages": [{"role": m["role"], "content": m["content"]} for m in conv],
                        "metadata": meta,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 2. pairwise judge cases from turn-1 human judgments without ties
    votes: dict[tuple[int, str, str], list[str]] = defaultdict(list)
    first: dict[tuple[int, str, str], dict] = {}
    for r in rows:
        if r["turn"] != 1:
            continue
        key = (r["question_id"], r["model_a"], r["model_b"])
        votes[key].append(r["winner"])
        first.setdefault(key, r)
    candidates = defaultdict(list)
    for key, vs in sorted(votes.items()):
        top = Counter(vs).most_common()
        if top[0][0] == "tie" or (len(top) > 1 and top[1][1] == top[0][1]):
            continue
        candidates[category(key[0])].append((key, top[0][0], len(vs)))
    rng = random.Random(args.seed)
    per_cat = args.pairs // len(CATEGORIES)
    chosen = []
    for cat in CATEGORIES:
        pool = candidates[cat]
        chosen += rng.sample(pool, min(per_cat, len(pool)))
    cases, labels = [], []
    for i, (key, winner, nvotes) in enumerate(chosen, 1):
        r = first[key]
        cid = f"pair-{i:03d}"
        cases.append(
            {
                "id": cid,
                "trace_id": f"q{key[0]}-{key[1]}-vs-{key[2]}",
                "status": "ready",
                "input": r["conversation_a"][0]["content"],
                "observed_output": r["conversation_a"][1]["content"],
                "compare_output": r["conversation_b"][1]["content"],
                "expected_behavior": "The more helpful, relevant, accurate and detailed answer to "
                "the user's question wins.",
                "criteria": ["overall-quality"],
                "tags": [f"category:{category(key[0])}", f"model_a:{key[1]}", f"model_b:{key[2]}"],
            }
        )
        labels.append(
            {
                "case_id": cid,
                "label": "A" if winner == "model_a" else "B",
                "human_votes": nvotes,
                "source": "MT-Bench expert judgment, turn 1",
            }
        )
    with open(out / "pairs_cases.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"suite": "MT-Bench pairwise judge check", "version": 1, "cases": cases},
            f,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
    with open(out / "pairs_labels.jsonl", "w", encoding="utf-8") as f:
        for lab in labels:
            f.write(json.dumps(lab) + "\n")
    print(
        json.dumps(
            {
                "dataset": REPO,
                "revision": REVISION,
                "sha256": SHA256,
                "rows": len(rows),
                "conversations": len(convs),
                "feedback": dict(
                    Counter(_feedback(record[k]["win"], record[k]["loss"]) or "none" for k in convs)
                ),
                "pair_candidates": {c: len(v) for c, v in candidates.items()},
                "pairs": len(cases),
                "label_counts": dict(Counter(lab["label"] for lab in labels)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
