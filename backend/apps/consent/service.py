"""Consent lifecycle (spec §21, §45, §60): record cookie + marketing consent as
append-only logs, and read the current state honestly (necessary always on,
optional off until opted in, marketing off by default)."""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.consent.models import CookieConsent, MarketingConsent, OPTIONAL_CATEGORIES


class ConsentError(Exception):
    pass


# --- cookie consent ----------------------------------------------------------

def record_cookie_consent(*, user=None, anon_id="", categories=None, policy_version="",
                          method="banner", jurisdiction="", ip_address=None,
                          user_agent="") -> CookieConsent:
    if user is None and not anon_id:
        raise ConsentError("Cookie consent needs a user or an anonymous id.")
    cats = categories or {}
    record = CookieConsent.objects.create(
        user=user if getattr(user, "pk", None) else None,
        anon_id=(anon_id or "")[:64],
        necessary=True,   # necessary cookies are never optional
        preferences=bool(cats.get("preferences")),
        analytics=bool(cats.get("analytics")),
        marketing=bool(cats.get("marketing")),
        policy_version=policy_version[:20], method=method[:24],
        jurisdiction=(jurisdiction or "")[:40], ip_address=ip_address,
        user_agent=(user_agent or "")[:400])
    audit("consent.cookies", actor=user if getattr(user, "pk", None) else None,
          target=f"cookie:{record.id}",
          summary=", ".join(c for c in OPTIONAL_CATEGORIES if cats.get(c)) or "necessary only")
    return record


def current_cookie_consent(*, user=None, anon_id="") -> CookieConsent | None:
    if getattr(user, "pk", None):
        return CookieConsent.objects.filter(user=user).first()
    if anon_id:
        return CookieConsent.objects.filter(anon_id=anon_id).first()
    return None


def cookie_allowed(category: str, *, user=None, anon_id="") -> bool:
    """Is a cookie category allowed for this subject? Necessary is always allowed;
    an optional category is allowed only if the latest consent opted into it."""
    if category == "necessary":
        return True
    record = current_cookie_consent(user=user, anon_id=anon_id)
    return bool(record and record.allowed(category))


def cookie_state(*, user=None, anon_id="") -> dict:
    record = current_cookie_consent(user=user, anon_id=anon_id)
    return {
        "necessary": True,
        "preferences": bool(record and record.preferences),
        "analytics": bool(record and record.analytics),
        "marketing": bool(record and record.marketing),
        "recorded": record is not None,
        "recorded_at": record.created_at.isoformat() if record else None,
    }


# --- marketing consent (separate from service communications) ----------------

def set_marketing_consent(user, opted_in: bool, *, source="settings",
                          policy_version="") -> MarketingConsent:
    record = MarketingConsent.objects.create(
        user=user, opted_in=bool(opted_in), source=source[:40],
        policy_version=policy_version[:20])
    audit("consent.marketing", actor=user, target=f"user:{user.id}",
          summary="opted in" if opted_in else "opted out")
    return record


def marketing_opted_in(user) -> bool:
    """Opt-in model: marketing is off unless the latest record opted in."""
    latest = MarketingConsent.objects.filter(user=user).first()
    return bool(latest and latest.opted_in)
