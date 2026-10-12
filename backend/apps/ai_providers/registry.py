"""Registry of AI providers, and the gateway used to call them.

The gateway is the single entry point the rest of the platform uses to run a
completion. It resolves a provider (explicit, or the configured default) and
delegates. The Model Router (Phase 7) will layer smart provider/model selection
on top of this; today the choice is "explicit provider, or the default".
"""
from __future__ import annotations

from dataclasses import replace

from django.conf import settings

from apps.ai_providers.anthropic_provider import AnthropicProvider
from apps.ai_providers.base import AIProvider, CompletionRequest, CompletionResponse
from apps.ai_providers.gemini_provider import GeminiProvider
from apps.ai_providers.openai_provider import OpenAIProvider
from apps.ai_providers.stub import StubProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> AIProvider:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' already registered")
        self._providers[provider.name] = provider
        return provider

    def get(self, name: str) -> AIProvider:
        return self._providers[name]

    def all(self) -> list[AIProvider]:
        return list(self._providers.values())

    def __contains__(self, name: str) -> bool:
        return name in self._providers


registry = ProviderRegistry()
registry.register(StubProvider())
registry.register(AnthropicProvider())
registry.register(OpenAIProvider())
registry.register(GeminiProvider())


def default_provider_name() -> str:
    # Defaults to the offline stub so a fresh checkout runs with no keys.
    return getattr(settings, "AI_DEFAULT_PROVIDER", "stub")


def live_providers() -> list:
    """Real (non-stub) models that are actually available right now."""
    return [p for p in registry.all() if getattr(p, "name", "") != "stub" and p.is_available()]


def generation_available() -> bool:
    """True when a real AI model is connected (not the offline stub)."""
    return bool(live_providers())


def generation_status() -> dict:
    """Honest status for the UI: is real AI generation available, and what to do if not."""
    live = live_providers()
    if live:
        return {"live": True, "provider": live[0].name,
                "message": f"Connected to {live[0].name} — real generation is enabled."}
    return {"live": False, "provider": None,
            "message": ("No AI model connected — code generation runs in offline demo mode. "
                        "Set an API key (e.g. ANTHROPIC_API_KEY) to enable real app generation.")}


# --- Pre-build balance check -------------------------------------------------
#
# generation_available()/live_providers() only check that a key is *set* and the
# SDK imports — they can't tell a funded account from one with no usable credit.
# That gap is why a build can silently fall back to the offline stub. preflight()
# closes it by making the smallest possible real request (1 token) to each
# connected provider: a success means the account can actually serve a build; a
# ProviderUnavailable (402/429/400 low-balance, etc.) means it can't right now.
# The result is cached for a few minutes so the build screen stays cheap.

_PREFLIGHT_CACHE_KEY = "ai:preflight"
_PREFLIGHT_TTL = 300  # seconds
_PROBE_TIMEOUT = 8  # seconds — a balance check must stay snappy, never hang the page


def _probe_provider(provider, timeout: float = _PROBE_TIMEOUT) -> dict:
    """Smallest real request that proves a provider can serve a build right now.

    Bounded by a wall-clock timeout: a provider SDK can retry on 429 with backoff,
    so the probe runs in a worker thread and is abandoned (reported unreachable) if
    it overruns, rather than blocking the request that called it.
    """
    import threading

    from apps.ai_providers.base import CompletionRequest, Message, ProviderUnavailable

    outcome: dict = {}

    def _run():
        try:
            provider.complete(CompletionRequest(
                messages=[Message(role="user", content="ping")], max_tokens=1))
            outcome.update(name=provider.name, ok=True, reason="")
        except ProviderUnavailable as exc:
            outcome.update(name=provider.name, ok=False, reason=str(exc))
        except Exception as exc:  # a probe must never crash the page that calls it
            outcome.update(name=provider.name, ok=False, reason=str(exc))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive() or not outcome:
        return {"name": provider.name, "ok": False,
                "reason": f"no response within {int(timeout)}s"}
    return outcome


def preflight(force: bool = False) -> dict:
    """Actively check which connected providers can serve a build right now.

    Returns {"ready": bool, "provider": name|None, "checked": [{name, ok, reason}],
    "stale": bool, "probed": bool}. `stale` means the result came from cache.
    Cached for _PREFLIGHT_TTL; pass force=True to probe again. Never makes network
    calls under tests.
    """
    from django.core.cache import cache

    if getattr(settings, "RUNNING_TESTS", False):
        return {"ready": False, "provider": None, "checked": [], "stale": False, "probed": False}

    if not force:
        cached = cache.get(_PREFLIGHT_CACHE_KEY)
        if cached is not None:
            return {**cached, "stale": True}

    providers = live_providers()
    if providers:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            checked = list(pool.map(_probe_provider, providers))
    else:
        checked = []
    ready_name = next((c["name"] for c in checked if c["ok"]), None)
    result = {"ready": ready_name is not None, "provider": ready_name,
              "checked": checked, "probed": True}
    cache.set(_PREFLIGHT_CACHE_KEY, result, _PREFLIGHT_TTL)
    return {**result, "stale": False}


def cached_preflight() -> dict | None:
    """Last probe result without triggering a new one — for cheap page renders."""
    if getattr(settings, "RUNNING_TESTS", False):
        return None
    from django.core.cache import cache
    cached = cache.get(_PREFLIGHT_CACHE_KEY)
    return {**cached, "stale": True} if cached is not None else None


def build_readiness(force: bool = False, probe: bool = True) -> dict:
    """UI-facing verdict on whether the next build will run on a real model.

    state is "none" (no model connected), "ready" (a model answered a live probe),
    "no_credit" (models connected but none could serve — e.g. out of credit), or
    "unknown" (not probed yet; shown with a Check button). Set probe=False to read
    only the cached verdict without making a call.
    """
    live = live_providers()
    if not live:
        return {"state": "none", "ready": False, "provider": None, "checked": [],
                "message": "No AI model is connected — builds run in offline demo mode "
                           "until an API key is set."}

    pf = preflight(force=force) if probe else (cached_preflight() or {"probed": False})
    if not pf.get("probed") and not pf.get("checked"):
        names = ", ".join(p.name for p in live)
        return {"state": "unknown", "ready": False, "provider": None, "checked": [],
                "message": f"Connected: {names}. Run a check to confirm it can build right now."}
    if pf.get("ready"):
        return {"state": "ready", "ready": True, "provider": pf["provider"],
                "checked": pf["checked"], "stale": pf.get("stale", False),
                "message": f"Real generation ready — {pf['provider']} responded."}
    return {"state": "no_credit", "ready": False, "provider": None,
            "checked": pf["checked"], "stale": pf.get("stale", False),
            "message": "AI models are connected but none can serve a build right now "
                       "(e.g. no usable credit) — builds will run in offline demo mode."}


def get_provider(name: str | None = None) -> AIProvider:
    resolved = name or default_provider_name()
    if resolved not in registry:
        raise ValueError(f"Unknown AI provider '{resolved}'")
    return registry.get(resolved)


def complete(request: CompletionRequest, *, provider=None) -> CompletionResponse:
    """Run a completion through the given provider (instance or name) or default."""
    prov = provider if isinstance(provider, AIProvider) else get_provider(provider)
    if request.model is None:
        request = replace(request, model=prov.default_model())
    return prov.complete(request)
