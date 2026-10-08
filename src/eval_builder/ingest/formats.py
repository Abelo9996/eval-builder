"""Parsers for each supported log format. Each yields normalized Trace objects."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from ..schema import FEEDBACK_KEYS, Trace, build_trace, normalize_feedback, text_of


class SkipRecord(Exception):
    """Raised when a record cannot become a trace; the message is the reason."""


FORMATS = ("openai", "anthropic", "langfuse", "otel", "generic")


# --------------------------------------------------------------------------- detection


def detect_format(records: list[Any]) -> str:
    """Guess the format from the first few records. Raises ValueError if unsure."""
    votes: dict[str, int] = {}
    for rec in records[:20]:
        fmt = _detect_one(rec)
        if fmt:
            votes[fmt] = votes.get(fmt, 0) + 1
    if not votes:
        raise ValueError(
            "could not detect the log format; pass --format "
            "(openai, anthropic, langfuse, otel, generic)"
        )
    return max(votes.items(), key=lambda kv: kv[1])[0]


def _detect_one(rec: Any) -> str | None:
    if not isinstance(rec, dict):
        return None
    if (
        "resourceSpans" in rec
        or "spanId" in rec
        or "span_id" in rec
        or (isinstance(rec.get("context"), dict) and "span_id" in rec["context"])
    ):
        return "otel"
    if "observations" in rec or "htmlPath" in rec or "projectId" in rec:
        return "langfuse"
    if _looks_anthropic(rec):
        return "anthropic"
    if (
        "messages" in rec
        or "choices" in rec
        or (isinstance(rec.get("request"), dict) and "messages" in rec["request"])
    ):
        return "openai"
    if "input" in rec and "output" in rec and isinstance(rec.get("scores"), list):
        return "langfuse"
    if any(k in rec for k in ("input", "prompt", "question")) and any(
        k in rec for k in ("output", "completion", "answer", "response")
    ):
        return "generic"
    return None


def _looks_anthropic(rec: dict[str, Any]) -> bool:
    req = _sub(rec, "request")
    resp = rec.get("response")
    if (
        isinstance(resp, dict)
        and isinstance(resp.get("content"), list)
        and ("stop_reason" in resp or resp.get("type") == "message")
    ):
        return True
    if rec.get("type") == "message" and isinstance(rec.get("content"), list):
        return True
    if isinstance(req, dict) and "messages" in req:
        if isinstance(req.get("system"), (str, list)) and "choices" not in rec:
            return True
        for m in req.get("messages") or []:
            content = m.get("content") if isinstance(m, dict) else None
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                for b in content
            ):
                return True
    return False


# --------------------------------------------------------------------------- helpers

_RESERVED_OPENAI = {
    "messages",
    "request",
    "response",
    "choices",
    "metadata",
    "id",
    "model",
    "usage",
    "object",
    "created",
    "system_fingerprint",
    "tools",
}


def _scalar_extras(rec: dict[str, Any], reserved: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if k in reserved:
            continue
        if (
            isinstance(v, (str, int, float, bool))
            or v is None
            or isinstance(v, list)
            and all(isinstance(x, (str, int, float)) for x in v)
        ):
            out[k] = v
    return out


def _sub(rec: dict[str, Any], key: str) -> dict[str, Any]:
    """rec[key] when it is a dict, else rec itself (flat records)."""
    v = rec.get(key)
    return v if isinstance(v, dict) else rec


def _dict_or_empty(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _openai_tool_names(msg: dict[str, Any]) -> list[str]:
    names = []
    for tc in msg.get("tool_calls") or []:
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            name = fn.get("name") or tc.get("name")
            if name:
                names.append(str(name))
    fc = msg.get("function_call")
    if isinstance(fc, dict) and fc.get("name"):
        names.append(str(fc["name"]))
    return names


# --------------------------------------------------------------------------- openai


def parse_openai(rec: dict[str, Any], file: str, index: int) -> Trace:
    req = _sub(rec, "request")
    messages = list(req.get("messages") or [])
    resp = _sub(rec, "response")
    choices = resp.get("choices") if isinstance(resp, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {"role": "assistant", "content": choices[0].get("text")}
        messages.append(msg)
    if not messages:
        raise SkipRecord("no messages")
    tools: list[str] = []
    for m in messages:
        if isinstance(m, dict):
            tools.extend(_openai_tool_names(m))
    md = dict(rec.get("metadata") or {}) if isinstance(rec.get("metadata"), dict) else {}
    md.update(_scalar_extras(rec, _RESERVED_OPENAI))
    model = rec.get("model") or req.get("model") or (resp.get("model") if resp else None)
    err = bool(rec.get("error")) or bool(isinstance(resp, dict) and resp.get("error"))
    return build_trace(
        [m for m in messages if isinstance(m, dict)],
        fmt="openai",
        file=file,
        index=index,
        given_id=rec.get("id"),
        tools=tools,
        metadata=md,
        model=model if isinstance(model, str) else None,
        error=err,
    )


# --------------------------------------------------------------------------- anthropic


def _anthropic_message(m: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    content = m.get("content")
    role = m.get("role", "user")
    if isinstance(content, list):
        texts = []
        only_tool_results = bool(content)
        for b in content:
            if not isinstance(b, dict):
                texts.append(str(b))
                only_tool_results = False
                continue
            btype = b.get("type")
            if btype == "tool_use":
                if b.get("name"):
                    tools.append(str(b["name"]))
                continue
            if btype == "tool_result":
                texts.append(text_of(b.get("content")))
                continue
            only_tool_results = False
            if btype in ("text", None):
                texts.append(text_of(b))
        if role == "user" and only_tool_results:
            role = "tool"
        return {"role": role, "content": "\n".join(t for t in texts if t)}
    return {"role": role, "content": text_of(content)}


def parse_anthropic(rec: dict[str, Any], file: str, index: int) -> Trace:
    req = _sub(rec, "request")
    tools: list[str] = []
    messages = [
        _anthropic_message(m, tools) for m in req.get("messages") or [] if isinstance(m, dict)
    ]
    resp = rec.get("response") if isinstance(rec.get("response"), dict) else None
    if resp is None and rec.get("type") == "message" and "content" in rec and rec is not req:
        resp = rec
    if resp is not None and isinstance(resp.get("content"), list):
        messages.append(
            _anthropic_message({"role": "assistant", "content": resp["content"]}, tools)
        )
    if not messages:
        raise SkipRecord("no messages")
    system = req.get("system")
    md = dict(rec.get("metadata") or {}) if isinstance(rec.get("metadata"), dict) else {}
    md.update(_scalar_extras(rec, _RESERVED_OPENAI | {"system", "type", "content", "stop_reason"}))
    if resp is not None and resp.get("stop_reason"):
        md["stop_reason"] = resp["stop_reason"]
    model = req.get("model") or (resp or {}).get("model")
    err = bool(rec.get("error")) or (resp is not None and resp.get("type") == "error")
    return build_trace(
        messages,
        fmt="anthropic",
        file=file,
        index=index,
        given_id=rec.get("id") or (resp or {}).get("id"),
        system=text_of(system) if system else None,
        tools=tools,
        metadata=md,
        model=model if isinstance(model, str) else None,
        error=err,
    )


# --------------------------------------------------------------------------- langfuse

_TEXT_KEYS = (
    "input",
    "query",
    "question",
    "prompt",
    "text",
    "content",
    "message",
    "output",
    "answer",
    "completion",
    "response",
    "result",
)


def _lf_messages(value: Any, default_role: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if (
        isinstance(value, list)
        and value
        and all(isinstance(m, dict) and "role" in m for m in value)
    ):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("messages"), list):
            return _lf_messages(value["messages"], default_role)
        if "role" in value and "content" in value:
            return [value]
        if isinstance(value.get("choices"), list) and value["choices"]:
            msg = value["choices"][0].get("message")
            if isinstance(msg, dict):
                return [msg]
        for key in _TEXT_KEYS:
            if isinstance(value.get(key), str):
                return [{"role": default_role, "content": value[key]}]
        return [{"role": default_role, "content": json.dumps(value, ensure_ascii=False)}]
    if isinstance(value, str):
        return [{"role": default_role, "content": value}]
    return [{"role": default_role, "content": text_of(value)}]


def parse_langfuse(rec: dict[str, Any], file: str, index: int) -> Trace:
    observations = [o for o in rec.get("observations") or [] if isinstance(o, dict)]
    generations = [o for o in observations if o.get("type") == "GENERATION"]
    generations.sort(key=lambda o: str(o.get("startTime") or ""))
    inp, out = rec.get("input"), rec.get("output")
    model = None
    tools: list[str] = []
    if generations:
        last = generations[-1]
        model = last.get("model")
        if inp is None:
            inp = last.get("input")
        if out is None:
            out = last.get("output")
    for o in observations:
        if o.get("type") == "TOOL" and o.get("name"):
            tools.append(str(o["name"]))
        if o.get("type") == "GENERATION":
            for m in _lf_messages(o.get("output"), "assistant"):
                tools.extend(_openai_tool_names(m))
    messages = _lf_messages(inp, "user")
    out_msgs = _lf_messages(out, "assistant")
    if out_msgs:
        final = out_msgs[-1]
        messages = messages + [{"role": "assistant", "content": final.get("content")}]
        tools.extend(_openai_tool_names(final))
    if not messages:
        raise SkipRecord("no input or output")
    error = any(str(o.get("level", "")).upper() == "ERROR" for o in observations)
    if str(rec.get("level", "")).upper() == "ERROR":
        error = True
    feedback = None
    other_scores: dict[str, Any] = {}
    for s in rec.get("scores") or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).lower().replace("-", "_").replace(" ", "_")
        value = s.get("value", s.get("stringValue"))
        if name in FEEDBACK_KEYS or "feedback" in name or "thumb" in name:
            feedback = feedback or normalize_feedback(value)
        else:
            other_scores[s.get("name", "score")] = value
    md = dict(rec.get("metadata") or {}) if isinstance(rec.get("metadata"), dict) else {}
    if rec.get("tags"):
        md["tags"] = rec["tags"]
    for key in ("release", "version", "environment"):
        if rec.get(key):
            md[key] = rec[key]
    if other_scores:
        md["scores"] = other_scores
    return build_trace(
        messages,
        fmt="langfuse",
        file=file,
        index=index,
        given_id=rec.get("id"),
        tools=tools,
        metadata=md,
        error=error,
        feedback=feedback,
        route=str(rec["name"]) if rec.get("name") else None,
        model=model if isinstance(model, str) else None,
    )


# --------------------------------------------------------------------------- otel


def _otel_value(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in v:
            return v[key]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return v["intValue"]
    if "arrayValue" in v:
        return [_otel_value(x) for x in (v["arrayValue"] or {}).get("values", [])]
    if "kvlistValue" in v:
        return {
            kv["key"]: _otel_value(kv.get("value")) for kv in v["kvlistValue"].get("values", [])
        }
    return v


def _otel_attrs(attrs: Any) -> dict[str, Any]:
    if isinstance(attrs, dict):
        return dict(attrs)
    out: dict[str, Any] = {}
    for kv in attrs or []:
        if isinstance(kv, dict) and "key" in kv:
            out[kv["key"]] = _otel_value(kv.get("value"))
    return out


def iter_otel_spans(rec: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Flatten OTLP JSON (resourceSpans) or pass through a single flat span."""
    if "resourceSpans" in rec:
        for rs in rec.get("resourceSpans") or []:
            res_attrs = _otel_attrs((rs.get("resource") or {}).get("attributes"))
            for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
                for span in ss.get("spans") or []:
                    yield {**span, "_resource": res_attrs}
    else:
        yield rec


def _span_trace_id(span: dict[str, Any]) -> str:
    ctx = _dict_or_empty(span.get("context"))
    return str(span.get("traceId") or span.get("trace_id") or ctx.get("trace_id") or "")


def _span_is_error(span: dict[str, Any]) -> bool:
    status = span.get("status") or {}
    code = status.get("code", status.get("status_code"))
    return code in (2, "2", "STATUS_CODE_ERROR", "ERROR") or bool(
        _otel_attrs(span.get("attributes")).get("error.type")
    )


def _parse_json_attr(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _semconv_messages(raw: Any, tools: list[str]) -> list[dict[str, Any]]:
    """gen_ai.input.messages / gen_ai.output.messages: [{role, parts:[{type, content}]}]."""
    raw = _parse_json_attr(raw)
    msgs: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return msgs
    for m in raw:
        if not isinstance(m, dict):
            continue
        parts = m.get("parts")
        if isinstance(parts, list):
            texts = []
            for p in parts:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "tool_call":
                    if p.get("name"):
                        tools.append(str(p["name"]))
                    continue
                if p.get("type") in ("text", "tool_call_response", None):
                    texts.append(text_of(p.get("content", p.get("response", p.get("result")))))
            content = "\n".join(t for t in texts if t)
        else:
            content = text_of(m.get("content"))
        role = m.get("role", "user")
        msgs.append({"role": "tool" if role == "tool" else role, "content": content})
    return msgs


def _indexed_messages(attrs: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    """OpenLLMetry style gen_ai.prompt.0.role / gen_ai.prompt.0.content."""
    idx: dict[int, dict[str, Any]] = {}
    for k, v in attrs.items():
        if not k.startswith(prefix + "."):
            continue
        rest = k[len(prefix) + 1 :].split(".", 1)
        if len(rest) == 2 and rest[0].isdigit() and rest[1] in ("role", "content"):
            idx.setdefault(int(rest[0]), {})[rest[1]] = v
    return [idx[i] for i in sorted(idx)]


def _event_messages(span: dict[str, Any]) -> list[dict[str, Any]]:
    msgs = []
    for ev in span.get("events") or []:
        name = ev.get("name", "")
        attrs = _otel_attrs(ev.get("attributes"))
        body = _parse_json_attr(ev.get("body", attrs.get("body")))
        payload = body if isinstance(body, dict) else attrs
        if name in (
            "gen_ai.system.message",
            "gen_ai.user.message",
            "gen_ai.assistant.message",
            "gen_ai.tool.message",
        ):
            role = name.split(".")[1]
            msgs.append({"role": role, "content": text_of(payload.get("content"))})
        elif name == "gen_ai.choice":
            message = _dict_or_empty(payload.get("message")) or payload
            msgs.append({"role": "assistant", "content": text_of(message.get("content"))})
    return msgs


def _span_messages(
    span: dict[str, Any], tools: list[str]
) -> tuple[list[dict[str, Any]], str | None]:
    attrs = _otel_attrs(span.get("attributes"))
    system = attrs.get("gen_ai.system_instructions")
    system_text = None
    if system is not None:
        parsed = _parse_json_attr(system)
        system_text = text_of(parsed) or (system if isinstance(system, str) else None)
    if "gen_ai.input.messages" in attrs or "gen_ai.output.messages" in attrs:
        msgs = _semconv_messages(attrs.get("gen_ai.input.messages"), tools)
        msgs += _semconv_messages(attrs.get("gen_ai.output.messages"), tools)
        return msgs, system_text
    prompt = _indexed_messages(attrs, "gen_ai.prompt")
    completion = _indexed_messages(attrs, "gen_ai.completion")
    if prompt or completion:
        return prompt + [
            {"role": m.get("role", "assistant"), "content": m.get("content")} for m in completion
        ], system_text
    if isinstance(attrs.get("gen_ai.prompt"), str) or isinstance(
        attrs.get("gen_ai.completion"), str
    ):
        msgs = []
        if attrs.get("gen_ai.prompt"):
            msgs.append({"role": "user", "content": attrs["gen_ai.prompt"]})
        if attrs.get("gen_ai.completion"):
            msgs.append({"role": "assistant", "content": attrs["gen_ai.completion"]})
        return msgs, system_text
    return _event_messages(span), system_text


_OTEL_META_SUFFIXES = {
    "route",
    "endpoint",
    "feature",
    "feedback",
    "user_feedback",
    "rating",
    "intent",
}


def parse_otel_trace(trace_id: str, spans: list[dict[str, Any]], file: str, index: int) -> Trace:
    def end_time(s: dict[str, Any]) -> int:
        try:
            return int(s.get("endTimeUnixNano") or s.get("end_time_unix_nano") or 0)
        except (TypeError, ValueError):
            return 0

    spans = sorted(spans, key=end_time)
    tools: list[str] = []
    llm_spans = []
    md: dict[str, Any] = {}
    model = None
    route = None
    error = False
    for s in spans:
        attrs = _otel_attrs(s.get("attributes"))
        op = attrs.get("gen_ai.operation.name")
        if op == "execute_tool" and attrs.get("gen_ai.tool.name"):
            tools.append(str(attrs["gen_ai.tool.name"]))
        if any(k.startswith("gen_ai.") for k in attrs) and op not in ("execute_tool", "embeddings"):
            llm_spans.append(s)
        error = error or _span_is_error(s)
        parent = s.get("parentSpanId") or s.get("parent_span_id") or s.get("parent_id")
        if not parent:
            route = route or attrs.get("gen_ai.agent.name") or s.get("name")
            for k, v in attrs.items():
                if not k.startswith("gen_ai.") and isinstance(v, (str, int, float, bool)):
                    md[k] = v
        for k, v in attrs.items():
            short = k.split(".")[-1]
            if short in _OTEL_META_SUFFIXES and not k.startswith("gen_ai.") and short not in md:
                md[short] = v
        res = s.get("_resource") or {}
        if res.get("service.name"):
            md.setdefault("service.name", res["service.name"])
    messages: list[dict[str, Any]] = []
    system = None
    for s in reversed(llm_spans):
        attrs = _otel_attrs(s.get("attributes"))
        msgs, system = _span_messages(s, tools)
        if msgs:
            messages = msgs
            model = attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model")
            provider = attrs.get("gen_ai.provider.name") or attrs.get("gen_ai.system")
            if provider:
                md["provider"] = provider
            break
    if not messages:
        raise SkipRecord("no gen_ai spans with message content (content capture may be off)")
    if isinstance(md.get("route"), str):
        route = md["route"]
    return build_trace(
        messages,
        fmt="otel",
        file=file,
        index=index,
        given_id=trace_id or None,
        system=system,
        tools=tools,
        metadata=md,
        error=error,
        route=str(route) if route else None,
        model=model if isinstance(model, str) else None,
    )


# --------------------------------------------------------------------------- generic


def parse_generic(rec: dict[str, Any], file: str, index: int) -> Trace:
    inp = next((rec[k] for k in ("input", "prompt", "question") if k in rec), None)
    out = next((rec[k] for k in ("output", "completion", "answer", "response") if k in rec), None)
    if inp is None:
        raise SkipRecord("no input field")
    messages = _lf_messages(inp, "user")
    if out is not None:
        out_msgs = _lf_messages(out, "assistant")
        if out_msgs:
            messages.append({"role": "assistant", "content": out_msgs[-1].get("content")})
    md = dict(rec.get("metadata") or {}) if isinstance(rec.get("metadata"), dict) else {}
    md.update(
        _scalar_extras(
            rec,
            {
                "input",
                "prompt",
                "question",
                "output",
                "completion",
                "answer",
                "response",
                "metadata",
                "id",
                "tools",
            },
        )
    )
    tools = [str(t) for t in rec.get("tools") or md.get("tools") or [] if isinstance(t, str)]
    if isinstance(md.get("tool"), str):
        tools.append(md["tool"])
    return build_trace(
        messages,
        fmt="generic",
        file=file,
        index=index,
        given_id=rec.get("id"),
        tools=tools,
        metadata=md,
    )


PARSERS = {
    "openai": parse_openai,
    "anthropic": parse_anthropic,
    "langfuse": parse_langfuse,
    "generic": parse_generic,
}
