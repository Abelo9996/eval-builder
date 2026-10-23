"""Judge model backends for `judge-check <judge>`: the one thing the user does not write.

A judge spec names a model and the orchestrator turns it into a callable that takes a
rendered prompt and a trial number and returns the judge's raw answer text. Supported:

    ollama:<model>              a local model served by Ollama (free, no key)
    openai:<model>              the OpenAI chat API, or any OpenAI-compatible base URL
    anthropic:<model>           the Anthropic messages API
    claude-code                 drive the installed `claude` CLI headlessly
    codex                       drive the installed `codex` CLI headlessly

Only the standard library is used, so eval-builder gains no dependency and ships no
keys: openai and anthropic read OPENAI_API_KEY / ANTHROPIC_API_KEY from the environment,
and the agent CLIs use whatever the user has already signed in.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_ID_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")

# Rough blended price per judge call (prompt + a few output tokens), US dollars. These
# are deliberately conservative over-estimates used only to warn before spending; the
# real bill comes from the provider. None means no per-call API charge we can estimate.
OPENAI_COST = 0.002
ANTHROPIC_COST = 0.003


class BackendError(RuntimeError):
    pass


@dataclass
class Backend:
    """A resolved judge: an id, how it bills, and a call that returns raw verdict text."""

    id: str
    kind: str
    model: str
    paid: bool
    note: str
    cost_per_call: float | None = None
    temperature: float = 0.7
    max_tokens: int = 16
    _opts: dict[str, Any] = field(default_factory=dict)

    def describe(self, calls: int) -> str:
        price = (
            f", about ${self.cost_per_call * calls:.2f} at ~${self.cost_per_call:.3f}/call"
            if self.cost_per_call
            else ", no per-call API charge"
        )
        return f"{self.kind} judge {self.model!r}: {calls} calls{price}. {self.note}"

    def __call__(self, prompt: str, trial: int) -> str:
        return _CALLERS[self.kind](self, prompt, trial)


def sanitize_id(spec: str) -> str:
    cleaned = _ID_SAFE.sub("-", spec).strip("-")
    return cleaned[:80] or "judge"


def parse_spec(
    spec: str,
    *,
    base_url: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 16,
) -> Backend:
    """Turn a judge spec string into a Backend. Pure: never touches the network."""
    spec = spec.strip()
    low = spec.lower()
    jid = sanitize_id(spec)
    if low in ("claude-code", "claude_code", "claudecode"):
        return Backend(
            id="claude-code",
            kind="claude-code",
            model="claude-code (haiku)",
            paid=False,
            note="drives your installed `claude` CLI headlessly on its cheapest model; "
            "slower than a local model and billed to your Claude plan.",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if low == "codex":
        return Backend(
            id="codex",
            kind="codex",
            model="codex (cheapest)",
            paid=False,
            note="drives your installed `codex` CLI headlessly; slower than a local model "
            "and billed to your OpenAI plan.",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if ":" not in spec:
        raise ValueError(
            f"judge spec {spec!r} not understood; use ollama:<model>, openai:<model>, "
            "anthropic:<model>, claude-code or codex"
        )
    prefix, model = spec.split(":", 1)
    prefix = prefix.strip().lower()
    model = model.strip()
    if not model:
        raise ValueError(f"judge spec {spec!r} has no model after the ':'")
    if prefix == "ollama":
        return Backend(
            id=jid,
            kind="ollama",
            model=model,
            paid=False,
            note="runs locally through Ollama; no API key, no per-call charge.",
            temperature=temperature,
            max_tokens=max_tokens,
            _opts={"host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")},
        )
    if prefix == "openai":
        url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip(
            "/"
        )
        local = any(h in url for h in ("127.0.0.1", "localhost", "0.0.0.0"))
        return Backend(
            id=jid,
            kind="openai",
            model=model,
            paid=not local,
            note=(
                f"OpenAI-compatible endpoint at {url}."
                + ("" if local else " Needs OPENAI_API_KEY; this spends money.")
            ),
            cost_per_call=None if local else OPENAI_COST,
            temperature=temperature,
            max_tokens=max_tokens,
            _opts={"base_url": url},
        )
    if prefix == "anthropic":
        return Backend(
            id=jid,
            kind="anthropic",
            model=model,
            paid=True,
            note="Anthropic messages API; needs ANTHROPIC_API_KEY. This spends money.",
            cost_per_call=ANTHROPIC_COST,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(
        f"unknown judge kind {prefix!r} in {spec!r}; use ollama, openai, anthropic, "
        "claude-code or codex"
    )


def preflight(backend: Backend) -> str | None:
    """A human-readable problem that would stop every call, or None if it looks runnable.

    Cheap, local checks only (a key in the environment, a CLI on PATH, Ollama answering).
    """
    if backend.kind == "ollama":
        host = backend._opts["host"]
        try:
            with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
                names = {m.get("name") for m in json.load(resp).get("models", [])}
        except (urllib.error.URLError, OSError) as e:
            return f"cannot reach Ollama at {host} ({e}); is `ollama serve` running?"
        if backend.model not in names and f"{backend.model}:latest" not in names:
            have = ", ".join(sorted(n for n in names if n)) or "none"
            return f"Ollama has no model {backend.model!r}; installed: {have}"
        return None
    if backend.kind == "openai" and backend.paid and not os.environ.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY is not set"
    if backend.kind == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY is not set"
    if backend.kind in ("claude-code", "codex"):
        exe = "claude" if backend.kind == "claude-code" else "codex"
        if shutil.which(exe) is None:
            return f"the {exe!r} CLI is not on PATH"
    return None


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise BackendError(f"{url} returned {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError) as e:
        raise BackendError(f"{url} failed: {e}") from e


def _call_ollama(b: Backend, prompt: str, trial: int) -> str:
    out = _post_json(
        f"{b._opts['host']}/api/generate",
        {
            "model": b.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": b.temperature,
                "seed": trial,
                "num_predict": b.max_tokens,
                "num_ctx": 8192,
            },
        },
        {},
        timeout=300,
    )
    return str(out.get("response", "")).strip()


def _call_openai(b: Backend, prompt: str, trial: int) -> str:
    headers = {}
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    out = _post_json(
        f"{b._opts['base_url']}/chat/completions",
        {
            "model": b.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": b.temperature,
            "max_tokens": b.max_tokens,
            "seed": trial,
        },
        headers,
        timeout=120,
    )
    return str(out["choices"][0]["message"]["content"]).strip()


def _call_anthropic(b: Backend, prompt: str, trial: int) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    out = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": b.model,
            "max_tokens": b.max_tokens,
            "temperature": b.temperature,
            "messages": [{"role": "user", "content": prompt}],
        },
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        timeout=120,
    )
    parts = [p.get("text", "") for p in out.get("content", []) if p.get("type") == "text"]
    return "".join(parts).strip()


def _call_cli(argv: list[str], prompt: str, timeout: float) -> str:
    try:
        proc = subprocess.run(
            argv, input=prompt, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as e:
        raise BackendError(f"{argv[0]!r} CLI not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise BackendError(f"{argv[0]!r} timed out after {timeout}s") from e
    if proc.returncode != 0:
        raise BackendError(f"{argv[0]!r} exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def _call_claude_code(b: Backend, prompt: str, trial: int) -> str:
    return _call_cli(["claude", "--print", "--model", "haiku"], prompt, timeout=180)


def _call_codex(b: Backend, prompt: str, trial: int) -> str:
    return _call_cli(["codex", "exec", "-"], prompt, timeout=180)


_CALLERS = {
    "ollama": _call_ollama,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "claude-code": _call_claude_code,
    "codex": _call_codex,
}
