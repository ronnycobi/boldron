"""Per-organization AI preferences — honest, soft routing hints.

An org can nudge which connected provider/model the Model Router favours for its
work. The preference is *soft*: the router only honours it when that provider or
model is actually available, and otherwise falls back to the normal policy, so a
preference can never break a build. Provider API keys are environment-only and are
never stored or exposed here — this module only reads which providers are
connected, never their secrets.
"""
from __future__ import annotations

from apps.organizations.models import OrgAiPreference


def preferences_for(org) -> dict:
    """The org's preference as a plain dict (empty strings when unset)."""
    pref = OrgAiPreference.objects.filter(organization=org).first()
    if not pref:
        return {"preferred_provider": "", "preferred_model": ""}
    return {
        "preferred_provider": pref.preferred_provider,
        "preferred_model": pref.preferred_model,
    }


def available_options() -> list[dict]:
    """Routable providers with their catalog models and live availability.

    Drives the settings UI: the user can only prefer something real. The offline
    stub is excluded — it's the no-key fallback, never a thing to prefer.
    """
    from apps.ai_providers.registry import registry
    from apps.model_router.catalog import MODEL_CATALOG

    out = []
    for provider in registry.all():
        if provider.name == "stub":
            continue
        models = [
            {"model": p.model, "label": p.model}
            for p in MODEL_CATALOG
            if p.provider == provider.name and not p.is_fallback_only
        ]
        out.append({
            "provider": provider.name,
            "available": provider.is_available(),
            "models": models,
        })
    return out


def _valid_provider(name: str) -> bool:
    return any(o["provider"] == name for o in available_options())


def _valid_model(provider: str, model: str) -> bool:
    for o in available_options():
        if o["provider"] == provider:
            return any(m["model"] == model for m in o["models"])
    return False


def set_preferences(org, *, preferred_provider: str = "", preferred_model: str = "",
                    actor=None) -> OrgAiPreference:
    """Validate and persist the org's AI preference. Unknown provider/model is
    rejected; blank clears the preference. A model without its provider is
    ignored (a model only makes sense alongside its provider)."""
    provider = (preferred_provider or "").strip()
    model = (preferred_model or "").strip()

    if provider and not _valid_provider(provider):
        raise ValueError("Unknown AI provider.")
    if model and not (provider and _valid_model(provider, model)):
        raise ValueError("That model isn't available for the selected provider.")

    pref, _ = OrgAiPreference.objects.get_or_create(organization=org)
    pref.preferred_provider = provider
    pref.preferred_model = model
    pref.save(update_fields=["preferred_provider", "preferred_model", "updated_at"])

    if actor is not None:
        from apps.settings.service import audit_change
        audit_change("organization.ai_updated", actor=actor, organization=org,
                     summary=f"AI preference → {provider or 'platform default'}"
                             f"{(':' + model) if model else ''}")
    return pref
