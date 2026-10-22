"""Anthropic Messages API adapter.

Targets Claude 4.6 and later (Opus/Sonnet/Haiku 5.5, Fable 5.1), which reject assistant
prefill and sampling parameters, think by default, and support JSON-schema structured output
through `output_config.format` (GA, no beta header). The system prompt is marked cacheable.
"""

from __future__ import annotations

import copy

from .base import LLMProvider, ProviderError, post_with_retry

# Thinking tokens count against max_tokens; leave room for them ahead of the JSON answer.
MAX_TOKENS = 16000


def strict_schema(schema: dict) -> dict:
    """Return a copy of `schema` with every object closed, as structured outputs require."""
    out = copy.deepcopy(schema)

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)

    close(out)
    return out


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def complete_json(self, system: str, user: str, schema: dict | None = None) -> str:
        if not self.settings.api_key:
            raise ProviderError("no API key configured (set ANTHROPIC_API_KEY)")
        url = self.settings.base_url.rstrip("/") + "/v1/messages"
        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict = {
            "model": self.settings.model,
            "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
        }
        output_config: dict = {}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": strict_schema(schema)}
        if self.settings.effort:
            output_config["effort"] = self.settings.effort
        if output_config:
            payload["output_config"] = output_config

        r = post_with_retry(self.name, url, payload, headers, self.settings.timeout)
        if r.status_code != 200:
            raise ProviderError(f"anthropic HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        stop = data.get("stop_reason")
        if stop in ("refusal", "max_tokens"):
            raise ProviderError(f"anthropic stopped with stop_reason={stop}; no usable answer")
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        if not text.strip():
            raise ProviderError(f"anthropic returned no text block: {str(data)[:300]}")
        return text

    def healthcheck(self) -> tuple[bool, str]:
        if not self.settings.api_key:
            return False, "no API key configured"
        return True, f"anthropic configured ({self.settings.model})"
