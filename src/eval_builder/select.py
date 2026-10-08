"""Pick a small, diverse, representative set of traces without calling any model.

Pipeline: exact dedupe (normalized text hash) -> near-duplicate merge (character
n-gram cosine) -> k-means topic clusters -> failure oversampling ->
stratum coverage -> one central example per cluster -> proportional fill with
farthest-point sampling. Every pick records the reasons it was picked.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from .ingest import load_traces
from .io import write_json
from .schema import Trace
from .workspace import Workspace

DEFAULT_STRATA = ("route", "tools", "error", "feedback")

_WS = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    return _WS.sub(" ", s.lower()).strip()


def text_hash(s: str) -> str:
    return hashlib.sha256(normalize_text(s).encode("utf-8")).hexdigest()


def is_failure(t: Trace) -> bool:
    return bool(t.error) or t.feedback == "negative"


def failure_kind(t: Trace) -> str:
    kinds = []
    if t.error:
        kinds.append("error flag")
    if t.feedback == "negative":
        kinds.append("negative user feedback")
    return " + ".join(kinds)


def user_text(t: Trace) -> str:
    """Everything the user said in the conversation, in order.

    Using only the last user message would merge unrelated conversations that end
    with the same generic follow-up ("make it shorter").
    """
    turns = [m["content"] for m in t.messages if m.get("role") == "user"]
    return "\n".join(turns) if turns else t.input


def _key_text(t: Trace, dedupe_on: str) -> str:
    return user_text(t) if dedupe_on == "input" else f"{user_text(t)}\n{t.output}"


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def near_duplicate_groups(texts: list[str], threshold: float, chunk: int = 1000) -> list[list[int]]:
    """Group texts whose character 3-5 gram cosine similarity is >= threshold."""
    n = len(texts)
    if n < 2:
        return [[i] for i in range(n)]
    # Plain term-frequency vectors (no IDF) so the similarity of two texts does not
    # depend on what else is in the corpus.
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, use_idf=False)
    try:
        x = vec.fit_transform(texts)
    except ValueError:  # all empty
        return [[i] for i in range(n)]
    uf = _UnionFind(n)
    for start in range(0, n, chunk):
        coo = sparse.coo_matrix(x[start : start + chunk] @ x.T)
        for r, c, v in zip(coo.row, coo.col, coo.data, strict=True):
            i = start + int(r)
            if int(c) > i and v >= threshold:
                uf.union(i, int(c))
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return sorted(groups.values(), key=lambda g: g[0])


def _pick_rep(members: list[int], traces: list[Trace]) -> int:
    for i in members:
        if is_failure(traces[i]):
            return i
    return members[0]


def _strata_values(t: Trace, field: str) -> list[str]:
    if field == "tools":
        return [f"{tool}" for tool in t.tools] or ["(none)"]
    if field == "error":
        return [str(bool(t.error)).lower()]
    if field == "feedback":
        return [t.feedback or "(none)"]
    if field == "route":
        return [t.route] if t.route else []
    if field == "model":
        return [t.model] if t.model else []
    cur: Any = t.metadata
    for part in field.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return []
    if isinstance(cur, list):
        return [str(x) for x in cur]
    return [str(cur)] if cur is not None else []


def select(
    workspace: str | Path,
    n: int = 50,
    seed: int = 0,
    clusters: int | None = None,
    failure_share: float = 0.3,
    near_dup_threshold: float = 0.9,
    dedupe_on: str = "input",
    stratify: list[str] | None = None,
) -> dict[str, Any]:
    if n < 1:
        raise ValueError("n must be >= 1")
    if dedupe_on not in ("input", "input+output"):
        raise ValueError("dedupe_on must be 'input' or 'input+output'")
    ws = Workspace.at(workspace)
    traces = load_traces(ws.root)
    if not traces:
        raise ValueError("no traces in workspace; run ingest first")
    result = select_traces(
        traces,
        n=n,
        seed=seed,
        clusters=clusters,
        failure_share=failure_share,
        near_dup_threshold=near_dup_threshold,
        dedupe_on=dedupe_on,
        stratify=stratify,
    )
    notes = []
    if result["selected_count"] < n:
        pop = result["population"]
        notes.append(
            f"asked for {n} cases but only {pop['unique']} unique traces remain after removing "
            f"{pop['exact_duplicates_removed']} exact and {pop['near_duplicates_merged']} near "
            "duplicates, so all of them were picked"
        )
    result["notes"] = notes
    result["next"] = "run draft to turn the selection into cases.yaml"
    write_json(ws.selection, result)
    return result


def select_traces(
    traces: list[Trace],
    n: int = 50,
    seed: int = 0,
    clusters: int | None = None,
    failure_share: float = 0.3,
    near_dup_threshold: float = 0.9,
    dedupe_on: str = "input",
    stratify: list[str] | None = None,
) -> dict[str, Any]:
    # 1. exact dedupe
    exact: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(traces):
        exact[text_hash(_key_text(t, dedupe_on))].append(i)
    exact_groups = sorted(exact.values(), key=lambda g: g[0])
    reps = [_pick_rep(g, traces) for g in exact_groups]
    members_of: dict[int, list[int]] = {r: g for r, g in zip(reps, exact_groups, strict=True)}

    # 2. near-duplicate merge among exact representatives
    near = near_duplicate_groups(
        [_key_text(traces[r], dedupe_on) for r in reps], near_dup_threshold
    )
    unique: list[int] = []
    group_members: dict[int, list[int]] = {}
    near_merged = 0
    for g in near:
        all_members = [m for gi in g for m in members_of[reps[gi]]]
        rep = _pick_rep(sorted(all_members), traces)
        unique.append(rep)
        group_members[rep] = sorted(all_members)
        if len(g) > 1:
            near_merged += len(g) - 1
    unique.sort()
    u_traces = [traces[i] for i in unique]
    nu = len(unique)

    # 3. topic clusters over the user side of each conversation
    vec = TfidfVectorizer(
        ngram_range=(1, 2), sublinear_tf=True, stop_words="english", max_features=20000, min_df=1
    )
    try:
        x = vec.fit_transform([user_text(t) for t in u_traces])
        terms = np.array(vec.get_feature_names_out())
    except ValueError:
        x = sparse.csr_matrix(np.ones((nu, 1)))
        terms = np.array(["(empty)"])
    k = clusters or max(2, round(math.sqrt(nu)))
    k = max(1, min(k, nu, n))
    if k >= 2:
        km = KMeans(n_clusters=k, n_init=10, random_state=seed)
        labels = km.fit_predict(x)
        centers = km.cluster_centers_
    else:
        labels = np.zeros(nu, dtype=int)
        centers = np.asarray(x.mean(axis=0))
    dense_dist = np.asarray(
        [np.linalg.norm(x[i].toarray().ravel() - centers[labels[i]]) for i in range(nu)]
    )
    cluster_info: list[dict[str, Any]] = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        top = [str(terms[j]) for j in np.argsort(-centers[c])[:5] if centers[c][j] > 0]
        cluster_info.append(
            {"id": c, "size": int(len(idx)), "share": round(len(idx) / nu, 4), "terms": top}
        )

    # helpers
    selected: dict[int, list[str]] = {}  # position in u_traces -> reasons

    def add(pos: int, reason: str) -> None:
        selected.setdefault(pos, []).append(reason)

    def central_order(positions: list[int]) -> list[int]:
        return sorted(positions, key=lambda p: (dense_dist[p], p))

    def cluster_note(c: int) -> str:
        info = cluster_info[c]
        terms = ", ".join(info["terms"][:3])
        return f"cluster {c} ({info['size']} traces, {info['share']:.0%}; {terms})"

    # 4. failure oversampling
    fail_pos = [p for p, t in enumerate(u_traces) if is_failure(t)]
    pop_fail_share = len(fail_pos) / nu if nu else 0.0
    fail_budget = min(
        len(fail_pos), n, max(math.ceil(failure_share * n), round(pop_fail_share * n))
    )
    if fail_budget:
        by_cluster: dict[int, list[int]] = defaultdict(list)
        for p in central_order(fail_pos):
            by_cluster[int(labels[p])].append(p)
        order = sorted(by_cluster, key=lambda c: (-cluster_info[c]["size"], c))
        picked = 0
        while picked < fail_budget:
            progressed = False
            for c in order:
                if by_cluster[c] and picked < fail_budget:
                    p = by_cluster[c].pop(0)
                    add(
                        p,
                        f"failure ({failure_kind(u_traces[p])}); {pop_fail_share:.0%} of unique "
                        f"traces are failures and at least {failure_share:.0%} of picks are "
                        f"reserved for them",
                    )
                    picked += 1
                    progressed = True
            if not progressed:
                break

    # 5. stratum coverage
    fields = list(DEFAULT_STRATA) + [f for f in (stratify or []) if f not in DEFAULT_STRATA]
    strata_pop: dict[str, Counter[str]] = {}
    skipped_fields: dict[str, str] = {}
    max_card = max(10, n // 2)
    for f in fields:
        counts: Counter[str] = Counter()
        for t in u_traces:
            counts.update(_strata_values(t, f))
        if not counts or (len(counts) == 1 and f in DEFAULT_STRATA):
            continue
        if len(counts) > max_card:
            skipped_fields[f] = f"{len(counts)} distinct values (limit {max_card})"
            continue
        strata_pop[f] = counts
    for f, counts in strata_pop.items():
        for value, cnt in sorted(counts.items(), key=lambda kv: (kv[1], kv[0])):
            if len(selected) >= n:
                break
            members = [p for p, t in enumerate(u_traces) if value in _strata_values(t, f)]
            if any(p in selected for p in members):
                continue
            p = central_order(members)[0]
            add(p, f"covers {f}={value} ({cnt} unique traces, {cnt / nu:.0%})")

    # 6. one central example per uncovered cluster
    covered = {int(labels[p]) for p in selected}
    for c in sorted(range(k), key=lambda c: (-cluster_info[c]["size"], c)):
        if len(selected) >= n:
            break
        if c in covered:
            continue
        members = [p for p in range(nu) if labels[p] == c]
        add(central_order(members)[0], f"central example of {cluster_note(c)}")

    # 7. proportional fill with farthest-point sampling inside each cluster
    remaining = n - len(selected)
    if remaining > 0:
        quotas = {c: n * cluster_info[c]["size"] / nu for c in range(k)}
        have = Counter(int(labels[p]) for p in selected)
        need = {c: max(0.0, quotas[c] - have[c]) for c in range(k)}
        floor = {c: int(need[c]) for c in range(k)}
        left = remaining - sum(floor.values())
        for c in sorted(range(k), key=lambda c: (-(need[c] - floor[c]), c)):
            if left <= 0:
                break
            floor[c] += 1
            left -= 1
        for c in range(k):
            for _ in range(floor[c]):
                if len(selected) >= n:
                    break
                far = _farthest(
                    x,
                    [q for q in range(nu) if labels[q] == c and q not in selected],
                    [q for q in selected if labels[q] == c],
                )
                if far is None:
                    break
                add(
                    far,
                    f"adds variety within {cluster_note(c)}; least similar to cases already "
                    f"picked there",
                )
        while len(selected) < min(n, nu):
            far = _farthest(x, [q for q in range(nu) if q not in selected], list(selected))
            if far is None:
                break
            add(far, "adds variety: least similar to every case already picked")

    # 8. assemble
    picks = []
    for p in sorted(selected, key=lambda p: (int(labels[p]), p)):
        t = u_traces[p]
        grp = group_members[unique[p]]
        picks.append(
            {
                "trace_id": t.id,
                "reasons": selected[p],
                "cluster": int(labels[p]),
                "represents": len(grp),
                "duplicates": [traces[i].id for i in grp if i != unique[p]],
                "failure": is_failure(t),
                "failing_in_group": sum(1 for i in grp if is_failure(traces[i])),
                "strata": {f: _strata_values(t, f) for f in strata_pop},
            }
        )
    sel_counts = Counter(int(labels[p]) for p in selected)
    for info in cluster_info:
        info["selected"] = sel_counts.get(info["id"], 0)
    strata_report = {
        f: {
            v: {
                "population": cnt,
                "selected": sum(1 for p in selected if v in _strata_values(u_traces[p], f)),
            }
            for v, cnt in sorted(counts.items())
        }
        for f, counts in strata_pop.items()
    }
    return {
        "params": {
            "n": n,
            "seed": seed,
            "clusters": k,
            "failure_share": failure_share,
            "near_dup_threshold": near_dup_threshold,
            "dedupe_on": dedupe_on,
            "stratify": fields,
        },
        "population": {
            "traces": len(traces),
            "exact_duplicates_removed": len(traces) - len(exact_groups),
            "near_duplicates_merged": near_merged,
            "unique": nu,
            "failures_unique": len(fail_pos),
        },
        "clusters": cluster_info,
        "strata": strata_report,
        "strata_skipped": skipped_fields,
        "selected_count": len(picks),
        "selected_failures": sum(1 for p in picks if p["failure"]),
        "selected": picks,
    }


def _farthest(x: sparse.csr_matrix, candidates: list[int], chosen: list[int]) -> int | None:
    if not candidates:
        return None
    if not chosen:
        return candidates[0]
    sims = (x[candidates] @ x[chosen].T).toarray()
    max_sim = sims.max(axis=1)
    best = int(np.argmin(max_sim))  # first index wins ties: deterministic
    return candidates[best]
