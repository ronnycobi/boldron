"""OpenAI (GPT) provider.

A real implementation: when the `openai` SDK is installed and OPENAI_API_KEY is set,
complete() calls the Chat Completions API. When either is missing, is_available() is
False and complete() raises ProviderUnavailable with a clear reason — an honest "not
configured", never a fabricated response. The key is read from the environment only;
it is never stored in settings, the database, or logs.
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


class OpenAIProvider(AIProvider):
    name = "openai"

    DEFAULT_MODEL = "gpt-4o"
    MODELS = ["gpt-4o", "gpt-4o-mini"]

    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def available_models(self) -> list[str]:
        return list(self.MODELS)

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        if not self._api_key():
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.is_available():
            raise ProviderUnavailable(
                "OpenAI provider unavailable: set OPENAI_API_KEY and install the "
                "'openai' package."
            )
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key())
        model = request.model or self.default_model()

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [{"role": m.role, "content": m.content} for m in request.messages]

        kwargs = {"model": model, "max_tokens": request.max_tokens, "messages": messages}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        response = client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        text = getattr(choice.message, "content", "") or ""
        usage = Usage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0),
            output_tokens=getattr(response.usage, "completion_tokens", 0),
        )
        return CompletionResponse(
            text=text,
            model=getattr(response, "model", model),
            provider=self.name,
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", "") or "",
        )
