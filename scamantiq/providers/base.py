from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod

import requests

from ..config import Settings

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 529})
MAX_ATTEMPTS = 4


class ProviderError(RuntimeError):
    """Raised when the LLM backend cannot be reached or returns an unusable answer."""


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def model(self) -> str:
        return self.settings.model

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: dict | None = None) -> str:
        """Return the model's raw text answer, expected to be a JSON object."""

    def healthcheck(self) -> tuple[bool, str]:
        return True, "not checked"


def post_with_retry(name: str, url: str, payload: dict, headers: dict, timeout: float) -> requests.Response:
    """POST JSON, retrying rate-limit and server errors with exponential backoff.

    Honours a `Retry-After` header when present. Returns the final response; non-retryable
    statuses are returned as-is so callers can inspect them. Raises ProviderError only when the
    request itself fails (connection error, timeout).
    """
    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            raise ProviderError(f"{name} request failed: {e}") from e
        if r.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
            return r
        wait = _retry_after(r)
        if wait is None:
            wait, delay = delay, min(delay * 2, 30.0)
        log.warning("%s HTTP %s, retrying in %.1fs (attempt %d/%d)", name, r.status_code, wait, attempt, MAX_ATTEMPTS)
        time.sleep(wait)
    raise AssertionError("unreachable")


def _retry_after(r: requests.Response) -> float | None:
    try:
        v = float(r.headers.get("retry-after", ""))
    except ValueError:
        return None
    return max(0.0, min(v, 60.0))


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json_object(text: str) -> dict:
    """Parse the first JSON object found in `text`, tolerating markdown fences and prose."""
    if not text or not text.strip():
        raise ProviderError("empty response from model")
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # find the outermost {...}
    start = cleaned.find("{")
    if start == -1:
        raise ProviderError(f"no JSON object in response: {text[:200]!r}")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError as e:
                    raise ProviderError(f"invalid JSON in response: {e}") from e
                if isinstance(obj, dict):
                    return obj
                break
    raise ProviderError(f"could not parse JSON object from response: {text[:200]!r}")
