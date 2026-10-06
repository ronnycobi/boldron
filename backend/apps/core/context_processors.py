"""Template context processors.

`brand` injects the product's display name (and tagline) into every template
rendered with a request context, so UI copy references {{ brand_name }} instead
of a hard-coded literal. This is the single source of truth for the visible brand
name — change settings.BRAND_NAME (or the DEVFORGE_BRAND_NAME env var) to rebrand
the whole UI at once.
"""
from __future__ import annotations

from django.conf import settings


def brand(request) -> dict:
    return {
        "brand_name": getattr(settings, "BRAND_NAME", "DevForge"),
        "brand_tagline": getattr(settings, "BRAND_TAGLINE", "AI software engineering"),
    }
