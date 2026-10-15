"""Data export (spec §25) — a real, honest copy of the user's own records.

Everything here is serialised from actual rows the caller already owns; nothing
is fabricated. Secrets are never included: API-key secrets are masked, a
project's secret env vars export their key only (never the value), and provider
credentials (environment-only) are not touched at all.
"""
from __future__ import annotations

from django.utils import timezone


def export_account(user) -> dict:
    """The signed-in user's own account data + their memberships."""
    return {
        "exported_at": timezone.now().isoformat(),
        "account": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "job_title": user.job_title,
            "pronouns": user.pronouns,
            "bio": user.bio,
            "language": user.language,
            "timezone": user.timezone,
            "email_verified": user.email_verified,
            "date_joined": user.date_joined.isoformat(),
        },
        "organizations": [
            {"id": m.organization_id, "name": m.organization.name, "role": m.role}
            for m in user.memberships.select_related("organization")
        ],
    }


def export_organization(org) -> dict:
    """A manager's export of the organization's own data (no secret values)."""
    from apps.developer.models import ApiKey, Webhook

    return {
        "exported_at": timezone.now().isoformat(),
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "description": org.description,
            "created_at": org.created_at.isoformat(),
        },
        "members": [
            {"email": m.user.email, "role": m.role,
             "joined": m.created_at.isoformat()}
            for m in org.memberships.select_related("user")
        ],
        "projects": [
            {
                "id": p.id, "name": p.name, "slug": p.slug, "status": p.status,
                "created_at": p.created_at.isoformat(),
                # Env var KEYS only — secret values are never exported.
                "env_var_keys": list(p.env_vars.values_list("key", flat=True)),
            }
            for p in org.projects.all()
        ],
        "api_keys": [
            {"name": k.name, "masked": k.masked, "active": k.is_active,
             "created_at": k.created_at.isoformat()}
            for k in ApiKey.objects.filter(organization=org)
        ],
        "webhooks": [
            {"url": w.url, "events": w.events, "active": w.active}
            for w in Webhook.objects.filter(organization=org)
        ],
    }
