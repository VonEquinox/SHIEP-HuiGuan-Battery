"""Small OpenAI-compatible cloud client. Credentials never enter run artifacts."""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-flash", proxy: str | None = "http://127.0.0.1:7897",
                 timeout: float = 60, retries: int = 1, transport: Any = None):
        url = urlparse(base_url)
        if url.scheme not in ("https", "http") or not url.netloc or url.username or url.password:
            raise ValueError("invalid cloud API base URL")
        if url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("remote cloud API must use HTTPS")
        if not api_key or not model:
            raise ValueError("API key and model are required")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.proxy = proxy
        self.timeout = min(max(float(timeout), 1), 120)
        self.retries = min(max(int(retries), 0), 2)
        self.transport = transport
        self.last_usage: dict[str, Any] = {}
        self.total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.request_count = 0
        self.failed_request_count = 0

    @classmethod
    def from_env(cls) -> "OpenAICompatibleClient | None":
        key = os.environ.get("BATTERY_LLM_API_KEY", "")
        if not key:
            return None
        return cls(api_key=key, base_url=os.environ.get("BATTERY_LLM_BASE_URL", "https://api.deepseek.com"),
                   model=os.environ.get("BATTERY_LLM_MODEL", "deepseek-flash"),
                   proxy=os.environ.get("BATTERY_LLM_PROXY", "http://127.0.0.1:7897") or None,
                   timeout=float(os.environ.get("BATTERY_LLM_TIMEOUT", "60")))

    def complete(self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None,
                 response_format: dict[str, Any] | None = None, temperature: float = 0.0) -> dict[str, Any]:
        request: dict[str, Any] = {"model": self.model, "messages": messages,
                                  "temperature": temperature, "max_tokens": 4096}
        if tools:
            request["tools"] = tools
        if response_format:
            request["response_format"] = response_format
        endpoint = self.base_url + "/chat/completions"
        for attempt in range(self.retries + 1):
            try:
                self.request_count += 1
                with httpx.Client(proxy=self.proxy if self.transport is None else None,
                                  timeout=self.timeout, transport=self.transport, trust_env=False) as client:
                    response = client.post(endpoint, json=request,
                                           headers={"Authorization": "Bearer " + self._api_key})
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    self.failed_request_count += 1
                    time.sleep(min(0.25 * (attempt + 1), 1))
                    continue
                if response.status_code >= 400:
                    self.failed_request_count += 1
                    # Provider bodies may echo request headers: retain only the status.
                    raise LLMError(f"cloud API returned HTTP {response.status_code}")
                result = response.json()
                if not isinstance(result, dict) or not result.get("choices"):
                    raise LLMError("cloud API response has no choices")
                self.last_usage = result.get("usage", {})
                for key in self.total_usage:
                    self.total_usage[key] += int(self.last_usage.get(key, 0))
                return result
            except (httpx.HTTPError, ValueError) as exc:
                self.failed_request_count += 1
                if attempt < self.retries:
                    continue
                raise LLMError("cloud API unavailable or returned invalid JSON") from None
        raise LLMError("cloud API exhausted request budget")

    def generate_json(self, messages: list[dict[str, Any]], *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        # json_object has broader compatibility than provider-specific strict schema.
        data = self.complete(messages, response_format={"type": "json_object"})
        try:
            result = json.loads(data["choices"][0]["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise LLMError("cloud API returned invalid structured content") from None
        if not isinstance(result, dict):
            raise LLMError("structured content must be an object")
        return result
