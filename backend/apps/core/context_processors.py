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


# Legal document types shown in the footer, in order (spec §58). Only the ones
# actually published appear — the footer is dynamic, never a dead link.
_FOOTER_TYPES = ["terms_of_service", "privacy_policy", "cookie_policy",
                 "acceptable_use_policy", "security_policy", "ai_terms"]


def legal_links(request) -> dict:
    """Published legal documents for the footer (dynamic, jurisdiction-global)."""
    try:
        from apps.legal.service import current
        links = []
        for t in _FOOTER_TYPES:
            doc = current(t)
            if doc:
                links.append({"title": doc.title, "slug": doc.slug})
        return {"footer_legal_links": links}
    except Exception:
        return {"footer_legal_links": []}
