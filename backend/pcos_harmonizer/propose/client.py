"""Thin OpenAI client wrapper for the propose step (the only LLM step)."""

from __future__ import annotations

import json
from typing import Any

from ..config import DEFAULT_MODEL, get_openai_api_key


class LLMClient:
    """Minimal JSON-in/JSON-out chat client with parse-retry."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key or get_openai_api_key()
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "openai is not installed; `pip install openai` or run in heuristic mode."
                ) from exc
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def complete_json(self, system: str, user: str, max_retries: int = 2) -> dict[str, Any]:
        """Call the model and parse a JSON object, retrying on parse failure."""
        client = self._ensure()
        last_err: Exception | None = None
        for _ in range(max_retries + 1):
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            text = resp.choices[0].message.content or ""
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last_err = exc
        raise ValueError(f"LLM did not return valid JSON after retries: {last_err}")

    def complete_text(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        """Free-text chat completion over a ``[{role, content}, ...]`` history.

        Used by the (read-only) data-chat assistant. Unlike :meth:`complete_json`
        this returns prose, not a parsed object, and keeps a small non-zero
        temperature so explanations read naturally.
        """
        client = self._ensure()
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


def get_default_client() -> LLMClient | None:
    """Return a client if an API key is configured, else None (→ heuristic mode)."""
    return LLMClient() if get_openai_api_key() else None
