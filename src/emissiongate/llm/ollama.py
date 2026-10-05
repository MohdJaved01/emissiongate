"""Ollama /api/chat client (httpx, non-streaming, JSON-schema `format`, explicit options)."""

from __future__ import annotations

import httpx


class OllamaTransport:
    def __init__(
        self,
        url: str,
        num_ctx: int,
        timeout_s: float = 600.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.num_ctx = num_ctx
        self._client = client or httpx.Client(timeout=timeout_s)

    def chat(
        self,
        model: str,
        think: str,
        messages: list[dict[str, str]],
        schema: dict,
        temperature: float,
    ) -> dict:
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "think": think,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        resp = self._client.post(f"{self.url}/api/chat", json=body)
        resp.raise_for_status()
        return resp.json()

    def available_models(self) -> list[str]:
        resp = self._client.get(f"{self.url}/api/tags", timeout=3.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
