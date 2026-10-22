"""Anthropic Messages adapter against a fake local server, using the Claude 5.5 request shape.

Claude 4.6 and later reject assistant prefill and sampling parameters, think by default
(thinking tokens count against max_tokens) and offer JSON-schema structured output through
`output_config.format`. These tests pin that request shape.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scamantiq.config import Settings
from scamantiq.providers.anthropic import AnthropicProvider, strict_schema
from scamantiq.providers.base import ProviderError
from scamantiq.schema import LLM_JSON_SCHEMA

ANSWER = {
    "is_suspicious": True,
    "summary": "Deadline pressure.",
    "tactics": [{"label": "urgency", "evidence": ["within 12 hours"], "explanation": "deadline", "confidence": 0.8}],
}


class FakeAnthropic:
    """Minimal POST /v1/messages server that records requests."""

    def __init__(self, stop_reason="end_turn", fail_first=None, with_thinking=True):
        self.requests: list[dict] = []
        self.stop_reason = stop_reason
        self.fail_first = fail_first  # HTTP status to return on the first request only
        self.with_thinking = with_thinking
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _send(self, code, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "json": payload})
                if outer.fail_first and len(outer.requests) == 1:
                    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
                    self._send(outer.fail_first, body, {"retry-after": "0"})
                    return
                content = []
                if outer.with_thinking:
                    content.append({"type": "thinking", "thinking": "", "signature": "sig"})
                content.append({"type": "text", "text": json.dumps(ANSWER)})
                self._send(
                    200,
                    {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": payload["model"],
                        "content": content,
                        "stop_reason": outer.stop_reason,
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                )

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"


def _settings(base_url, effort="", model="claude-opus-5-5"):
    return Settings(
        preset="anthropic", provider="anthropic", base_url=base_url, model=model, api_key="k", use_cache=False, timeout=10, effort=effort
    )


def test_request_shape_matches_claude_5_api():
    with FakeAnthropic() as srv:
        out = AnthropicProvider(_settings(srv.base_url)).complete_json("SYS", "USER", LLM_JSON_SCHEMA)
    assert json.loads(out) == ANSWER
    req = srv.requests[-1]
    assert req["path"] == "/v1/messages"
    assert req["headers"]["x-api-key"] == "k" and req["headers"]["anthropic-version"]
    body = req["json"]
    assert body["model"] == "claude-opus-5-5"
    assert [m["role"] for m in body["messages"]] == ["user"]  # no assistant prefill
    assert body["messages"][0]["content"] == "USER"
    assert "temperature" not in body and "top_p" not in body and "top_k" not in body
    assert body["system"][0]["text"] == "SYS" and body["system"][0]["cache_control"] == {"type": "ephemeral"}
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["tactics"]["items"]["additionalProperties"] is False
    assert "effort" not in body["output_config"]
    assert body["max_tokens"] >= 8000  # thinking tokens count against max_tokens


def test_effort_is_passed_through_when_configured():
    with FakeAnthropic() as srv:
        AnthropicProvider(_settings(srv.base_url, effort="low")).complete_json("s", "u", LLM_JSON_SCHEMA)
    assert srv.requests[-1]["json"]["output_config"]["effort"] == "low"


def test_text_block_is_returned_and_thinking_ignored():
    with FakeAnthropic(with_thinking=True) as srv:
        out = AnthropicProvider(_settings(srv.base_url)).complete_json("s", "u", LLM_JSON_SCHEMA)
    assert out == json.dumps(ANSWER)


def test_retries_on_429_then_succeeds(monkeypatch):
    import scamantiq.providers.base as base

    sleeps: list[float] = []
    monkeypatch.setattr(base.time, "sleep", lambda s: sleeps.append(s))
    with FakeAnthropic(fail_first=429) as srv:
        out = AnthropicProvider(_settings(srv.base_url)).complete_json("s", "u", LLM_JSON_SCHEMA)
    assert json.loads(out) == ANSWER
    assert len(srv.requests) == 2 and len(sleeps) == 1


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_or_truncation_raises(stop):
    with FakeAnthropic(stop_reason=stop) as srv:
        with pytest.raises(ProviderError, match=stop):
            AnthropicProvider(_settings(srv.base_url)).complete_json("s", "u", LLM_JSON_SCHEMA)


def test_strict_schema_closes_every_object_without_mutating_input():
    out = strict_schema(LLM_JSON_SCHEMA)
    assert out["additionalProperties"] is False
    assert out["properties"]["tactics"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in LLM_JSON_SCHEMA
