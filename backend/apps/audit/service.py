"""record() — the one call other apps use to write an audit event.

Best-effort: auditing must never break the action it records, so any failure is
swallowed. Keep call sites at real decision points (approvals, implementations,
migrations, deploys, membership changes), not in tight loops.
"""
from __future__ import annotations

from apps.audit.models import AuditEvent


def events_for(organization, *, limit=100):
    """Recent audit events for one organization, newest first (read-only)."""
    return list(
        AuditEvent.objects.filter(organization=organization)
        .select_related("actor")[:limit]
    )


def event_dict(e) -> dict:
    return {
        "id": e.id,
        "action": e.action,
        "actor": e.actor.email if e.actor_id else None,
        "target": e.target,
        "summary": e.summary,
        "created_at": e.created_at.isoformat(),
    }


def record(action, *, actor=None, organization=None, target="", summary="", metadata=None):
    try:
        return AuditEvent.objects.create(
            action=action, actor=actor, organization=organization,
            target=target or "", summary=(summary or "")[:500], metadata=metadata or {},
        )
    except Exception:
        return None
