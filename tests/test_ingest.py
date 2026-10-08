from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_builder.ingest import ingest, load_records, load_traces, parse_file
from eval_builder.ingest.formats import detect_format
from eval_builder.redact import Redactor
from eval_builder.schema import normalize_feedback


def by_id(traces):
    return {t.id: t for t in traces}


def test_openai_chat(fixtures: Path) -> None:
    fmt, traces, skipped, n = parse_file(fixtures / "openai_chat.jsonl")
    assert fmt == "openai" and n == 4 and len(traces) == 4 and not skipped
    first, weather, req3, cancel = traces
    assert first.system == "You are a support bot."
    assert first.input == "How do I reset my password?"
    assert first.output.startswith("Go to Settings")
    assert first.route == "account" and first.feedback == "positive"
    assert weather.tools == ["get_weather"]
    assert weather.output == "It's 18C and cloudy in Paris."
    assert [m["role"] for m in weather.messages] == ["user", "assistant", "tool", "assistant"]
    assert req3.id == "req-3" and req3.model == "gpt-4o-mini"
    assert req3.output == "Please rotate that key now."
    assert req3.feedback == "negative"  # top-level user_feedback: down
    assert cancel.error is True and cancel.route == "orders"


def test_anthropic_messages(fixtures: Path) -> None:
    fmt, traces, _, _ = parse_file(fixtures / "anthropic_messages.json")
    assert fmt == "anthropic" and len(traces) == 2
    haiku, calc = traces
    assert haiku.id == "msg_01" and haiku.system == "You are a coding assistant."
    assert haiku.output.startswith("Red then green") and haiku.model == "claude-sonnet-4-5"
    assert calc.tools == ["calculator"]
    assert calc.input == "What is 17 * 23?"  # the tool_result turn is not the user input
    assert calc.output == "17 * 23 = 391."
    assert calc.messages[2] == {"role": "tool", "content": "391"}
    assert calc.feedback == "positive"  # rating 5
    assert calc.prior_turns() == []


def test_langfuse_export(fixtures: Path) -> None:
    fmt, traces, _, _ = parse_file(fixtures / "langfuse_export.json")
    assert fmt == "langfuse" and len(traces) == 2
    t1, t2 = traces
    assert t1.id == "lf-trace-1" and t1.route == "rag-answer" and t1.model == "gpt-4o"
    assert t1.input == "What is our refund window?"
    assert t1.feedback == "negative"  # user-feedback score 0
    assert t1.metadata["scores"] == {"faithfulness": 0.9}
    assert t1.metadata["tags"] == ["rag"]
    # trace-level input/output null: falls back to the last generation
    assert t2.input == "Where is order 1234?" and t2.output == "I could not find that order."
    assert t2.system == "Be brief." and t2.tools == ["search_orders"] and t2.error is True


def test_otel_genai_spans(fixtures: Path) -> None:
    fmt, traces, skipped, _ = parse_file(fixtures / "otel_genai.json")
    assert fmt == "otel" and len(traces) == 2
    assert skipped == {"no gen_ai spans with message content (content capture may be off)": 1}
    billing, failed = traces
    assert billing.id == "aaaa0000000000000000000000000001"
    assert billing.system == "You help with billing."
    assert billing.input == "Why was I charged twice?"
    assert billing.output.startswith("The second charge")
    assert billing.tools == ["lookup_invoice"] and billing.model == "gpt-4o"
    assert billing.route == "billing" and billing.metadata["service.name"] == "support-agent"
    assert failed.error is True and failed.input == "Summarize my last invoice"


def test_otel_flat_console_spans(tmp_path: Path) -> None:
    span = {
        "name": "chat",
        "context": {"trace_id": "0xabc", "span_id": "0x1"},
        "parent_id": None,
        "status": {"status_code": "OK"},
        "attributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "m",
            "gen_ai.prompt": "hi there",
            "gen_ai.completion": "hello",
        },
    }
    p = tmp_path / "spans.jsonl"
    p.write_text(json.dumps(span) + "\n")
    fmt, traces, _, _ = parse_file(p)
    assert fmt == "otel" and traces[0].input == "hi there" and traces[0].output == "hello"


def test_generic_jsonl(fixtures: Path) -> None:
    fmt, traces, skipped, n = parse_file(fixtures / "generic.jsonl")
    assert fmt == "generic" and n == 4 and len(traces) == 3
    assert skipped == {"no input field": 1}
    assert traces[0].id == "g1" and traces[0].feedback == "positive"
    assert traces[2].error is True


def test_detect_format_unknown() -> None:
    with pytest.raises(ValueError, match="could not detect"):
        detect_format([{"foo": 1}])


def test_load_records_bad_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text('{"input": "a", "output": "b"}\nnot json\n')
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        load_records(p)


def test_ingest_directory_redacts_and_reports(tmp_path: Path, fixtures: Path) -> None:
    ws = tmp_path / "ws"
    r = ingest([fixtures], ws)
    assert r["traces"] == 13 and len(r["sources"]) == 5
    assert all(len(s["sha256"]) == 64 for s in r["sources"])
    red = r["redactions"]
    # one email, one key, one phone, one Luhn-valid card; each counted once
    assert red["by_kind"] == {"credit_card": 1, "email": 1, "openai_key": 1, "phone": 1}
    text = (ws / "traces.jsonl").read_text()
    assert "jane.doe@example.com" not in text and "sk-proj-" not in text
    assert "4111 1111 1111 1111" not in text and "555-0134" not in text
    assert "[REDACTED_EMAIL]" in text
    assert len(load_traces(ws)) == 13


def test_ingest_no_redact(tmp_path: Path, fixtures: Path) -> None:
    r = ingest([fixtures / "openai_chat.jsonl"], tmp_path / "ws", redact=False)
    assert r["redactions"]["enabled"] is False and r["redactions"]["total"] == 0
    assert "jane.doe@example.com" in (tmp_path / "ws" / "traces.jsonl").read_text()


def test_redactor_patterns() -> None:
    r = Redactor()
    assert r.text("card 4111111111111111 ok") == "card [REDACTED_CREDIT_CARD] ok"
    assert r.text("order 1234567890123") == "order 1234567890123"  # fails Luhn: kept
    assert r.text("AKIAABCDEFGHIJKLMNOP") == "[REDACTED_AWS_ACCESS_KEY]"
    assert r.text("x sk-ant-api03-abcdefghijklmnopqrstuvwxyz") == "x [REDACTED_ANTHROPIC_KEY]"
    assert r.text("ssn 123-45-6789") == "ssn [REDACTED_SSN]"
    assert r.text("the year 2023 and 12.5%") == "the year 2023 and 12.5%"


def test_normalize_feedback() -> None:
    assert normalize_feedback("thumbs_down") == "negative"
    assert normalize_feedback(True) == "positive"
    assert normalize_feedback(0) == "negative"
    assert normalize_feedback(1) == "positive"
    assert normalize_feedback(3) == "neutral"
    assert normalize_feedback(2) == "negative"
    assert normalize_feedback("maybe") is None
