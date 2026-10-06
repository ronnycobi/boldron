"""Google Gemini provider.

A real implementation on the supported `google-genai` SDK: when the SDK is
installed and a key is set (GOOGLE_API_KEY or GEMINI_API_KEY), complete() calls the
Gemini API. When either is missing, is_available() is False and complete() raises
ProviderUnavailable with a clear reason — an honest "not configured", never a
fabricated response. The key is read from the environment only; it is never stored
in settings, the database, or logs.
"""
from __future__ import annotations

import os

from apps.ai_providers.base import (
    AIProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderUnavailable,
    Usage,
)


class GeminiProvider(AIProvider):
    name = "gemini"

    # Use Google's stable "-latest" aliases rather than pinned version numbers:
    # Gemini's point versions churn fast and old ones get retired for new keys
    # (e.g. gemini-2.5-flash → 404 for new projects), so an alias keeps the
    # platform pointed at a current, generally-available model without edits.
    DEFAULT_MODEL = "gemini-flash-latest"
    MODELS = ["gemini-pro-latest", "gemini-flash-latest"]

    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def available_models(self) -> list[str]:
        return list(self.MODELS)

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

    def is_available(self) -> bool:
        if not self._api_key():
            return False
        try:
            from google import genai  # noqa: F401
        except ImportError:
            return False
        return True

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.is_available():
            raise ProviderUnavailable(
                "Gemini provider unavailable: set GOOGLE_API_KEY (or GEMINI_API_KEY) "
                "and install the 'google-genai' package."
            )
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        client = genai.Client(api_key=self._api_key())
        model_name = request.model or self.default_model()
        # Gemini roles: user / model (assistant -> model).
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in request.messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=request.system or None,
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        # Translate any API-level failure (capacity 503, rate-limit 429, auth,
        # bad request) into ProviderUnavailable so the router can fail over to
        # another provider instead of crashing the call. Transient Gemini 503s
        # are common, so this is the difference between a blip and an outage.
        try:
            response = client.models.generate_content(
                model=model_name, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise ProviderUnavailable(
                f"Gemini request to {model_name} failed"
                f"{f' ({code})' if code else ''}: {exc}"
            ) from exc

        text = getattr(response, "text", "") or ""
        meta = getattr(response, "usage_metadata", None)
        usage = Usage(
            input_tokens=getattr(meta, "prompt_token_count", 0) if meta else 0,
            output_tokens=getattr(meta, "candidates_token_count", 0) if meta else 0,
        )
        return CompletionResponse(
            text=text, model=model_name, provider=self.name, usage=usage,
        )
