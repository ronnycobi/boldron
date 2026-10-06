"""Template context processors.

`branding` injects the resolved application identity (name, tagline, company,
URL, logo, favicon, support contacts) into every template rendered with a request
context, so UI copy references {{ app_name }}, {{ app_logo_url }}, … instead of a
hard-coded brand. This is the single source of truth for the visible identity —
change the APP_* environment settings to rebrand the whole UI at once.
"""
from __future__ import annotations

from apps.core.branding import app_branding


def branding(request) -> dict:
    return app_branding()
