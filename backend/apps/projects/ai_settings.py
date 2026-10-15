"""Per-project AI preferences — soft routing hints that take precedence over the
organization's. Same honesty posture as apps.organizations.ai_settings: the
preference is only honoured when available, keys are never stored, and the stub
provider is never offered as a preference.
"""
from __future__ import annotations

from apps.organizations import ai_settings as org_ai
from apps.projects.models import ProjectAiPreference


def preferences_for(project) -> dict:
    """The preference the router should use for this project: the project's own
    choice when set, otherwise the organization's. A per-field fallback so a
    project can override just the provider or just the model."""
    org = org_ai.preferences_for(project.organization)
    pref = ProjectAiPreference.objects.filter(project=project).first()
    if pref is None:
        return org
    return {
        "preferred_provider": pref.preferred_provider or org["preferred_provider"],
        "preferred_model": pref.preferred_model or org["preferred_model"],
    }


def own_preferences(project) -> dict:
    """The project's own stored choice (empty when it inherits the org)."""
    pref = ProjectAiPreference.objects.filter(project=project).first()
    if pref is None:
        return {"preferred_provider": "", "preferred_model": ""}
    return {"preferred_provider": pref.preferred_provider,
            "preferred_model": pref.preferred_model}


# The routable options are the same platform-wide set the org picker uses.
available_options = org_ai.available_options


def set_preferences(project, *, preferred_provider="", preferred_model="",
                    actor=None) -> ProjectAiPreference:
    provider = (preferred_provider or "").strip()
    model = (preferred_model or "").strip()
    if provider and not org_ai._valid_provider(provider):
        raise ValueError("Unknown AI provider.")
    if model and not (provider and org_ai._valid_model(provider, model)):
        raise ValueError("That model isn't available for the selected provider.")

    pref, _ = ProjectAiPreference.objects.get_or_create(project=project)
    pref.preferred_provider = provider
    pref.preferred_model = model
    pref.save(update_fields=["preferred_provider", "preferred_model", "updated_at"])

    if actor is not None:
        from apps.settings.service import audit_change
        audit_change("project.ai_updated", actor=actor,
                     organization=project.organization,
                     summary=f"{project.name}: AI → {provider or 'inherit org'}"
                             f"{(':' + model) if model else ''}")
    return pref
