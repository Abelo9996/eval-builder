"""The normalized trace schema every ingest format maps into."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Trace:
    """One logged interaction, normalized.

    `input` is the last user message before the final assistant reply and `output`
    is that reply's text. `messages` keeps the whole conversation (including the
    final reply) so multi-turn context is never lost.
    """

    id: str
    input: str
    output: str
    messages: list[dict[str, str]] = field(default_factory=list)
    system: str | None = None
    tools: list[str] = field(default_factory=list)
    error: bool = False
    feedback: str | None = None  # "positive" | "negative" | "neutral" | None
    route: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Trace:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def prior_turns(self) -> list[dict[str, str]]:
        """Conversation before the last user message (the case input).

        Tool calls and intermediate assistant steps after that message are part of the
        app's behavior being evaluated, so they are not included.
        """
        last_user = max(
            (i for i, m in enumerate(self.messages) if m.get("role") == "user"), default=0
        )
        return list(self.messages[:last_user])


def text_of(content: Any) -> str:
    """Extract plain text from the many shapes providers use for message content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, list):
        parts = [text_of(p) for p in content]
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        ptype = content.get("type")
        if ptype in ("tool_use", "tool_call", "function_call", "image", "image_url", "input_image"):
            return ""
        for key in ("text", "content", "value", "output_text", "input_text"):
            if key in content:
                return text_of(content[key])
        return ""
    return str(content)


_FEEDBACK_POS = {
    "up",
    "thumbs_up",
    "thumbsup",
    "positive",
    "good",
    "like",
    "liked",
    "yes",
    "true",
    "+1",
    "1",
    "helpful",
    "pass",
    "correct",
}
_FEEDBACK_NEG = {
    "down",
    "thumbs_down",
    "thumbsdown",
    "negative",
    "bad",
    "dislike",
    "disliked",
    "no",
    "false",
    "-1",
    "0",
    "unhelpful",
    "fail",
    "incorrect",
    "wrong",
}


def normalize_feedback(value: Any) -> str | None:
    """Map thumbs, booleans, 0/1 and 1-5 ratings onto positive/negative/neutral."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "positive" if value else "negative"
    if isinstance(value, (int, float)):
        v = float(value)
        if v < 0:
            return "negative"
        if v <= 1:
            return "negative" if v < 0.5 else "positive"
        if v <= 5:
            if v <= 2:
                return "negative"
            return "positive" if v >= 4 else "neutral"
        return None
    if isinstance(value, str):
        s = value.strip().lower().replace(" ", "_")
        if s in _FEEDBACK_POS:
            return "positive"
        if s in _FEEDBACK_NEG:
            return "negative"
        if s in ("neutral", "meh", "mixed"):
            return "neutral"
        try:
            return normalize_feedback(float(s))
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("value", "score", "rating", "label"):
            if key in value:
                return normalize_feedback(value[key])
    return None


FEEDBACK_KEYS = ("feedback", "user_feedback", "thumbs", "rating", "user_rating", "vote")
ERROR_KEYS = ("error", "is_error", "failed", "exception")
ROUTE_KEYS = ("route", "endpoint", "path", "feature", "workflow", "task", "intent")


def fill_common_fields(trace: Trace) -> Trace:
    """Derive error, feedback and route from metadata when a format did not set them."""
    md = trace.metadata
    if trace.feedback is None:
        for key in FEEDBACK_KEYS:
            if key in md:
                trace.feedback = normalize_feedback(md[key])
                if trace.feedback:
                    break
    if not trace.error:
        for key in ERROR_KEYS:
            v = md.get(key)
            if v not in (None, False, "", 0, "false", "False", "none", "None"):
                trace.error = True
                break
        status = str(md.get("status", "")).lower()
        if status in ("error", "failed", "failure"):
            trace.error = True
    if trace.route is None:
        for key in ROUTE_KEYS:
            v = md.get(key)
            if isinstance(v, (str, int)) and str(v):
                trace.route = str(v)
                break
    if trace.model is None and isinstance(md.get("model"), str):
        trace.model = md["model"]
    return trace


_ID_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def make_id(*parts: Any, given: Any = None) -> str:
    if given not in (None, ""):
        cleaned = _ID_SAFE.sub("-", str(given)).strip("-")
        if cleaned:
            return cleaned[:80]
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return "t-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def build_trace(
    messages: list[dict[str, Any]],
    *,
    fmt: str,
    file: str,
    index: int,
    given_id: Any = None,
    system: str | None = None,
    tools: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    error: bool = False,
    feedback: str | None = None,
    route: str | None = None,
    model: str | None = None,
) -> Trace:
    """Build a Trace from role/content messages (content already flattened to text)."""
    norm: list[dict[str, str]] = []
    sys_parts: list[str] = [system] if system else []
    for m in messages:
        role = str(m.get("role", "user")).lower()
        if role in ("system", "developer"):
            t = text_of(m.get("content"))
            if t:
                sys_parts.append(t)
            continue
        if role in ("human",):
            role = "user"
        if role in ("ai", "model", "bot"):
            role = "assistant"
        norm.append({"role": role, "content": text_of(m.get("content"))})
    output = ""
    if norm and norm[-1]["role"] == "assistant":
        output = norm[-1]["content"]
    user_msgs = [m["content"] for m in norm if m["role"] == "user"]
    inp = user_msgs[-1] if user_msgs else ""
    trace = Trace(
        id=make_id(fmt, file, index, inp, output, given=given_id),
        input=inp,
        output=output,
        messages=norm,
        system="\n\n".join(sys_parts) or None,
        tools=sorted(set(tools or [])),
        error=error,
        feedback=feedback,
        route=route,
        model=model,
        metadata=dict(metadata or {}),
        source={"format": fmt, "file": file, "index": index},
    )
    return fill_common_fields(trace)
