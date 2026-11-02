"""Privacy-request lifecycle + secrets-safe export (spec §17-19)."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings as dj_settings
from django.utils import timezone

from apps.audit.service import record as audit
from apps.privacy.models import (
    OPEN_STATUSES,
    PrivacyRequest,
    PrivacyRequestEvent,
    RequestStatus,
    RequestType,
)

# How long the team has to resolve a request (configurable; not a legal claim).
SLA_DAYS = getattr(dj_settings, "PRIVACY_REQUEST_SLA_DAYS", 30)


class PrivacyError(Exception):
    pass


def submit(user, request_type, *, organization=None, jurisdiction="", details="") -> PrivacyRequest:
    if request_type not in RequestType.values:
        raise PrivacyError(f"Unknown request type '{request_type}'.")
    req = PrivacyRequest.objects.create(
        user=user, organization=organization, request_type=request_type,
        jurisdiction=(jurisdiction or "")[:40], details=(details or "")[:4000],
        deadline=timezone.now() + timedelta(days=SLA_DAYS))
    PrivacyRequestEvent.objects.create(
        request=req, kind="submitted", status=RequestStatus.RECEIVED, actor=user)
    audit("privacy.request", actor=user,
          organization=organization, target=f"privacy:{req.id}",
          summary=f"{request_type} request")
    return req


def transition(req: PrivacyRequest, status: str, *, note="", actor=None) -> PrivacyRequest:
    if status not in RequestStatus.values:
        raise PrivacyError(f"Unknown status '{status}'.")
    req.status = status
    if status == RequestStatus.VERIFIED:
        req.identity_verified = True
    if status not in OPEN_STATUSES and not req.resolved_at:
        req.resolved_at = timezone.now()
    elif status in OPEN_STATUSES:
        req.resolved_at = None
    req.save()
    PrivacyRequestEvent.objects.create(
        request=req, kind="status", status=status, note=(note or "")[:2000], actor=actor)
    audit("privacy.transition", actor=actor, organization=req.organization,
          target=f"privacy:{req.id}", summary=f"{req.request_type} -> {status}")
    return req


def assign(req: PrivacyRequest, reviewer, *, actor=None) -> PrivacyRequest:
    req.assigned_to = reviewer
    req.save(update_fields=["assigned_to", "updated_at"])
    PrivacyRequestEvent.objects.create(
        request=req, kind="assigned", note=getattr(reviewer, "email", ""), actor=actor)
    return req


def resolve(req: PrivacyRequest, *, resolution="", status=RequestStatus.COMPLETED,
            actor=None) -> PrivacyRequest:
    req.resolution = (resolution or "")[:4000]
    req.save(update_fields=["resolution", "updated_at"])
    return transition(req, status, note=resolution, actor=actor)


def add_note(req: PrivacyRequest, note, *, actor=None) -> PrivacyRequestEvent:
    return PrivacyRequestEvent.objects.create(
        request=req, kind="note", note=(note or "")[:2000], actor=actor)


def summary() -> dict:
    reqs = PrivacyRequest.objects.all()
    return {
        "total": reqs.count(),
        "open": reqs.filter(status__in=OPEN_STATUSES).count(),
        "overdue": reqs.filter(status__in=OPEN_STATUSES,
                               deadline__lt=timezone.now()).count(),
    }


# --- data export (secrets excluded) ------------------------------------------

def build_export(user) -> dict:
    """Compose the user's exportable data. Reuses the platform's existing export
    composer, which NEVER includes secret values (API-key secrets masked, env vars
    key-only). This function additionally guarantees no secret-looking keys leak."""
    from apps.settings.data_export import export_account
    data = export_account(user)
    return _strip_secrets(data)


_SECRET_HINTS = ("password", "secret", "private_key", "signing_key", "token_value",
                 "card_number", "cvv", "encryption_key")


def _strip_secrets(obj):
    """Defence in depth: drop any key that looks like a credential value."""
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if any(h in str(k).lower() for h in _SECRET_HINTS):
                continue
            clean[k] = _strip_secrets(v)
        return clean
    if isinstance(obj, list):
        return [_strip_secrets(v) for v in obj]
    return obj
