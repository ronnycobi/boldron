"""Unified external-integration status (spec §23) — one honest readiness view.

Every third-party integration the platform can use sits behind a credential that
comes from the ENVIRONMENT only. This module aggregates the real, env-gated status
of all of them into one place — connectors (GitHub, Slack, Google/SSO, WhatsApp,
external Postgres), payment gateways (Stripe, PayFast), and SMS gateways (Twilio,
Africa's Talking) — so the customer sees exactly what is connected and what isn't.

Nothing here reports a connection that isn't real: each entry's `connected` flag is
the genuine "is the credential present" check its subsystem already uses, never a
fabricated "enabled". The actual credential value is never read, stored or returned —
only the name of the environment variable that would enable it.
"""
from __future__ import annotations


def _connectors() -> list[dict]:
    from apps.tools.connectors import connector_status
    out = []
    for c in connector_status():
        out.append({
            "key": c["key"], "name": c["provider"], "category": "connector",
            "connected": c["configured"], "credential_env": c["credential_env"],
        })
    return out


def _payment_gateways() -> list[dict]:
    from apps.publishing.payments import _PROVIDERS
    out = []
    for key, prov in _PROVIDERS.items():
        if key == "manual":
            continue   # manual is a real built-in, not an external integration
        out.append({
            "key": key, "name": prov.name, "category": "payment",
            "connected": prov.is_available(),
            "credential_env": getattr(prov, "env_var", ""),
        })
    return out


def _sms_gateways() -> list[dict]:
    from apps.notifications import sms
    return [{
        "key": p["key"], "name": p["name"], "category": "sms",
        "connected": p["available"], "detail": p["detail"],
    } for p in sms.provider_status()]


def integration_status() -> dict:
    """The full, honest inventory of external integrations and their real state."""
    items = _connectors() + _payment_gateways() + _sms_gateways()
    connected = sum(1 for i in items if i["connected"])
    return {
        "integrations": items,
        "total": len(items),
        "connected": connected,
        "all_gated": connected == 0,
    }
