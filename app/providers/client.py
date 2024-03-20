"""Provider-neutral HTTP adapters. Only explicit opt-in can cause network traffic."""

import os
import re
import threading
import time
from urllib.parse import urlparse

import httpx

from app.core.models import ProviderProfile

LOCK = threading.Lock()


class ProviderError(ValueError):
    pass


def endpoint(profile):
    url = profile.base_url.rstrip("/")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError("Base URL must be HTTP(S), without credentials, query or fragment")
    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "host.docker.internal",
    }:
        raise ProviderError("Remote providers require HTTPS")
    return url


class ProviderClient:
    def __init__(self, store, transport=None):
        self.store = store
        self.transport = transport

    def _request(self, p, method, path, body=None):
        key = os.environ.get(p.key_env, "")
        if p.kind not in {"ollama", "offline"} and not key:
            raise ProviderError(f"Server environment variable {p.key_env} is not configured")
        headers = {"Content-Type": "application/json"}
        if p.kind == "anthropic":
            headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        elif key:
            headers["Authorization"] = f"Bearer {key}"
        # Never include request/response bodies or secrets in error messages/logs.
        with httpx.Client(
            timeout=p.timeout, transport=self.transport, follow_redirects=False, trust_env=False
        ) as client:
            for attempt in range(3):
                try:
                    response = client.request(
                        method, endpoint(p) + path, headers=headers, json=body
                    )
                except httpx.RequestError as exc:
                    raise ProviderError(
                        "Provider connection failed or timed out; no secret details logged"
                    ) from exc
                if response.status_code in {429, 502, 503} and attempt < 2:
                    time.sleep(min(2**attempt, 4))
                    continue
                if response.status_code >= 300:
                    raise ProviderError(
                        f"Provider HTTP {response.status_code}; check endpoint, credentials and model"
                    )
                try:
                    if len(response.content) > 1024 * 1024:
                        raise ProviderError("Provider response exceeds 1 MiB")
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ProviderError("Provider returned an unexpected response shape")
                    return data
                except ValueError as exc:
                    raise ProviderError("Provider returned non-JSON data") from exc

    def models(self, p: ProviderProfile, opt_in=False):
        if p.kind == "offline":
            return ["offline-reference-demo"]
        if not opt_in:
            raise ProviderError("Explicit network opt-in is required")
        data = self._request(p, "GET", "/api/tags" if p.kind == "ollama" else "/models")
        items = data.get("models" if p.kind == "ollama" else "data", [])
        if not isinstance(items, list) or any(not isinstance(m, dict) for m in items):
            raise ProviderError("Unexpected model list response")
        models = (
            [m.get("name") for m in data.get("models", [])]
            if p.kind == "ollama"
            else [m.get("id") for m in data.get("data", [])]
        )
        return sorted(m for m in models if isinstance(m, str))

    def generate(self, p: ProviderProfile, prompt: str, opt_in=False):
        if len(prompt) > 12000:
            raise ProviderError("Prompt exceeds 12000 characters")
        if p.kind == "offline":
            # Explicit deterministic fixture, never represented as an AI model.
            return {
                "provider": p.name,
                "model": "offline-reference-demo",
                "formula": "=SUM(B2:B100)",
                "latency_seconds": 0,
                "usage": {},
                "estimated_cost_usd": 0,
                "notice": "Offline fixture for sales_total only; not a generated AI prediction.",
            }
        if not opt_in:
            raise ProviderError(
                "Enable outbound requests explicitly. Prompts may contain private spreadsheet data."
            )
        with LOCK:
            previous = self.store.usage(p.name)
            if len(previous) >= p.request_limit:
                raise ProviderError("Provider lifetime request limit reached")
            # Reserve a conservative maximum before network use. Unknown price ->
            # budgets cannot safely be enforced, so refuse budgeted requests.
            reserve = None
            if p.input_per_million is not None and p.output_per_million is not None:
                reserve = (
                    (
                        (len(prompt.encode("utf-8")) + 200) * p.input_per_million
                        + p.max_tokens * p.output_per_million
                    )
                    * 3
                    / 1e6
                )
            if p.budget_usd is not None:
                if (
                    reserve is None
                    or sum(u.get("cost_reserved", 0) for u in previous) + reserve > p.budget_usd
                ):
                    raise ProviderError(
                        "Budget requires explicit prices and sufficient remaining allowance"
                    )
            self.store.record_usage(p.name, {"cost_reserved": reserve or 0, "state": "reserved"})
        if not p.model:
            try:
                available = self.models(p, True)
            except ProviderError as exc:
                raise ProviderError(
                    "Model discovery unavailable. Supply a confirmed model identifier."
                ) from exc
            if not available:
                raise ProviderError("No discoverable models; provide a model identifier")
            p = p.model_copy(update={"model": available[0]})
        started = time.monotonic()
        messages = [
            {
                "role": "user",
                "content": "Return exactly one Excel formula beginning with =, no prose. " + prompt,
            }
        ]
        if p.kind == "anthropic":
            data = self._request(
                p,
                "POST",
                "/messages",
                {
                    "model": p.model,
                    "messages": messages,
                    "max_tokens": p.max_tokens,
                    "temperature": p.temperature,
                },
            )
            text = "".join(
                c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"
            )
            usage = data.get("usage", {})
            inputs, outputs = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        elif p.kind == "ollama":
            data = self._request(
                p,
                "POST",
                "/api/chat",
                {
                    "model": p.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": p.temperature, "num_predict": p.max_tokens},
                },
            )
            text = data.get("message", {}).get("content", "")
            inputs, outputs = data.get("prompt_eval_count", 0), data.get("eval_count", 0)
            usage = {"input_tokens": inputs, "output_tokens": outputs}
        else:
            data = self._request(
                p,
                "POST",
                "/chat/completions",
                {
                    "model": p.model,
                    "messages": messages,
                    "max_tokens": p.max_tokens,
                    "temperature": p.temperature,
                },
            )
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            inputs, outputs = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        if not isinstance(text, str):
            raise ProviderError("Provider formula content must be plain text")
        if not isinstance(usage, dict):
            raise ProviderError("Unexpected token usage response")
        usage = {k: v for k, v in usage.items() if isinstance(v, int) and not isinstance(v, bool)}
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[^\n]*\n|\n```$", "", text).strip()
        if not text.startswith("=") or len(text) > 2000 or "\n" in text:
            raise ProviderError("Provider did not return one bounded formula")
        cost = (
            (inputs * p.input_per_million + outputs * p.output_per_million) / 1e6
            if p.input_per_million is not None and p.output_per_million is not None
            else None
        )
        return {
            "provider": p.name,
            "model": p.model,
            "formula": text,
            "latency_seconds": round(time.monotonic() - started, 3),
            "usage": usage,
            "estimated_cost_usd": cost,
            "reserved_cost_usd": reserve,
        }
