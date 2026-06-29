"""Thin Gemini client over the OpenAI-compatible endpoint.

Matches UlamAI's default `base_url` (https://generativelanguage.googleapis.com/v1beta/openai),
so the same auth/env works whether the loop drives UlamAI or calls Gemini
directly (the faithfulness back-translation judge and the fallback driver).

Auth (in priority order):
  GEMINI_API_KEY / ULAM_GEMINI_API_KEY      -> AI-Studio key (fastest to start)
  ULAM_GEMINI_BASE_URL                       -> override to a Vertex OpenAI-compat
                                                gateway for grant-billed cost.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


def _api_key() -> str:
    for var in ("GEMINI_API_KEY", "ULAM_GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    raise RuntimeError(
        "No Gemini key found. Set GEMINI_API_KEY (AI-Studio) or point "
        "ULAM_GEMINI_BASE_URL at a Vertex OpenAI-compatible gateway."
    )


class Gemini:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        from openai import OpenAI  # lazy import so the module loads without the dep

        self.model = model or os.environ.get("ULAM_GEMINI_MODEL", "gemini-3.1-pro-preview")
        self.base_url = base_url or os.environ.get("ULAM_GEMINI_BASE_URL", DEFAULT_BASE_URL)
        self.client = OpenAI(api_key=_api_key(), base_url=self.base_url)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> Completion:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        m = model or self.model
        resp = self.client.chat.completions.create(
            model=m, messages=msgs, temperature=temperature
        )
        usage = resp.usage
        return Completion(
            text=resp.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=m,
        )
