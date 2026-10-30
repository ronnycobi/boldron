"""Integration marketplace (spec §12) — one categorised catalogue of every external
service the platform can connect, with an HONEST status composed from the real
subsystems (no status is invented or duplicated here).

Each integration reports one of:
  - "connected"  : genuinely configured and usable right now (real credential/backend).
  - "available"  : a built-in that works today with no connection needed (e.g. manual
                   payments, the platform's own analytics, built-in file storage).
  - "connect"    : the adapter is built but needs the customer's credentials — it
                   refuses rather than fakes until connected (Stripe, Twilio, …).
  - "planned"    : on the roadmap, not built yet.

The lifecycle the UI shows (SEARCH → CONNECT → CONFIGURE → VERIFY → TEST → ACTIVATE)
is represented honestly: an integration is only "connected" when its subsystem says a
real credential/backend is present — never on an optimistic assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CONNECTED = "connected"
AVAILABLE = "available"
CONNECT = "connect"
PLANNED = "planned"

# Display order of categories (spec §12).
CATEGORIES = ["Payments", "Email", "AI", "Authentication", "Communication",
              "Storage", "Analytics", "Developer"]


@dataclass(frozen=True)
class Integration:
    id: str
    name: str
    category: str
    description: str
    credential_env: tuple[str, ...] = ()   # env var NAMES that connect it (never values)


# The static catalogue. Status is resolved live by _status() below.
_CATALOG = [
    # Payments
    Integration("manual", "Manual / EFT", "Payments", "Bank transfer & invoice payments, confirmed by you."),
    Integration("stripe", "Stripe", "Payments", "Card payments worldwide.", ("STRIPE_SECRET_KEY",)),
    Integration("payfast", "PayFast", "Payments", "South African card & EFT payments.", ("PAYFAST_MERCHANT_ID",)),
    # Email
    Integration("email", "Email delivery", "Email", "Transactional & campaign email.", ("EMAIL_HOST",)),
    # AI
    Integration("anthropic", "Anthropic", "AI", "Claude models for generation.", ("ANTHROPIC_API_KEY",)),
    Integration("openai", "OpenAI", "AI", "GPT models for generation.", ("OPENAI_API_KEY",)),
    Integration("gemini", "Google Gemini", "AI", "Gemini models for generation.", ("GEMINI_API_KEY",)),
    # Authentication / connectors
    Integration("google", "Google Workspace", "Authentication", "Sign-in (SSO) and data.", ("GOOGLE_OAUTH_CLIENT_ID",)),
    # Communication
    Integration("twilio", "Twilio", "Communication", "SMS messaging.", ("TWILIO_ACCOUNT_SID",)),
    Integration("africastalking", "Africa's Talking", "Communication", "SMS messaging.", ("AT_API_KEY",)),
    Integration("slack", "Slack", "Communication", "Notifications and actions.", ("SLACK_BOT_TOKEN",)),
    Integration("whatsapp", "WhatsApp", "Communication", "Messaging via the WhatsApp Business API.", ("WHATSAPP_TOKEN",)),
    # Storage
    Integration("files", "File storage", "Storage", "Built-in private & public uploads with thumbnails."),
    # Analytics
    Integration("analytics", "Analytics", "Analytics", "Built-in visitors, events and conversions."),
    # Developer
    Integration("github", "GitHub / GitLab", "Developer", "Import and connect repositories.", ("GITHUB_TOKEN",)),
]

_BY_ID = {i.id: i for i in _CATALOG}


def _status(integration_id: str) -> tuple[str, str]:
    """(status, detail) for one integration, from the REAL subsystem that owns it."""
    i = integration_id
    # Payments
    if i in ("stripe", "payfast", "manual"):
        from apps.publishing.payments import provider_status
        row = next((p for p in provider_status() if p["key"] == i), None)
        if i == "manual":
            return AVAILABLE, "Works today — no connection needed."
        if row and row["available"]:
            return CONNECTED, "Connected."
        return CONNECT, "Add your keys to accept card payments."
    # Email — real when EMAIL_BACKEND is SMTP and a host is set; console = dev only.
    if i == "email":
        from django.conf import settings as dj
        backend = getattr(dj, "EMAIL_BACKEND", "")
        if "smtp" in backend.lower() and getattr(dj, "EMAIL_HOST", ""):
            return CONNECTED, "Live email delivery is configured."
        return AVAILABLE, "Sends via the development backend; connect SMTP for live delivery."
    # AI providers
    if i in ("anthropic", "openai", "gemini"):
        from apps.ai_providers.registry import live_providers
        live = {p.name for p in live_providers()}
        if i in live:
            return CONNECTED, "Connected — real generation enabled."
        return CONNECT, "Add an API key to enable real generation."
    # Connectors (github/slack/google/whatsapp)
    if i in ("github", "slack", "google", "whatsapp"):
        from apps.tools.connectors import connector_status
        row = next((c for c in connector_status() if c["key"] == i), None)
        if row and row["configured"]:
            return CONNECTED, "Connected."
        return CONNECT, "Connect credentials to enable."
    # SMS gateways
    if i in ("twilio", "africastalking"):
        from apps.notifications import sms
        row = next((p for p in sms.provider_status() if p["key"] == i), None)
        if row and row["available"]:
            return CONNECTED, "Connected."
        return CONNECT, row["detail"] if row else "Connect credentials to enable."
    # Built-ins that are genuinely available today
    if i in ("files", "analytics"):
        return AVAILABLE, "Built in — available today."
    return PLANNED, "On the roadmap."


def _entry(integration: Integration) -> dict:
    status, detail = _status(integration.id)
    return {
        "id": integration.id,
        "name": integration.name,
        "category": integration.category,
        "description": integration.description,
        "status": status,
        "connected": status == CONNECTED,
        "usable": status in (CONNECTED, AVAILABLE),
        "detail": detail,
        "credential_env": list(integration.credential_env),
    }


def marketplace() -> dict:
    """The full categorised marketplace with honest, live status per integration."""
    entries = [_entry(i) for i in _CATALOG]
    groups = []
    for cat in CATEGORIES:
        items = [e for e in entries if e["category"] == cat]
        if items:
            groups.append({"category": cat, "items": items})
    return {
        "groups": groups,
        "total": len(entries),
        "connected": sum(1 for e in entries if e["connected"]),
        "usable": sum(1 for e in entries if e["usable"]),
    }
