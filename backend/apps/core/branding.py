"""Central application-branding layer.

The single place customer-facing identity is resolved from configuration. Nothing
else in the codebase should read a brand value from anywhere but here (templates
go through the `branding` context processor, which calls this). Changing the APP_*
settings — i.e. the environment — rebrands the whole product; no source changes.

Internal platform concepts (agents, projects, builds, deployments, capabilities,
providers, commerce, …) are deliberately NOT part of this layer.
"""
from __future__ import annotations

from django.conf import settings


def app_branding() -> dict:
    """Resolved, template-ready branding. Empty optional values fall back sensibly
    (company -> app name) so a minimally-configured deployment still renders."""
    name = settings.APP_NAME
    return {
        "app_name": name,
        "app_company_name": settings.APP_COMPANY_NAME or name,
        "app_tagline": settings.APP_TAGLINE,
        "app_url": settings.APP_URL,
        "app_logo_url": settings.APP_LOGO_URL,
        "app_favicon_url": settings.APP_FAVICON_URL,
        "app_support_email": settings.APP_SUPPORT_EMAIL,
        "app_support_url": settings.APP_SUPPORT_URL,
        "app_default_currency": settings.APP_DEFAULT_CURRENCY,
    }
