"""Incident lifecycle service (spec §20).

Opening, timeline, transitions, resolution and auto-detection. The honesty rule
(spec §20): moving an incident to resolved/closed is an explicit human action — the
AI may analyse and recommend, but `analyze()` never changes the status.
"""
from __future__ import annotations

from django.utils import timezone

from apps.audit.service import record as audit
from apps.incidents.models import Incident, IncidentEvent, IncidentStatus


class IncidentError(Exception):
    pass


def open_incident(project, *, title, severity="medium", source="manual", detail="",
                  deployment=None, user=None) -> Incident:
    title = (title or "").strip()
    if not title:
        raise IncidentError("An incident needs a title.")
    incident = Incident.objects.create(
        project=project, deployment=deployment, title=title[:200],
        severity=severity, source=source, detail=(detail or "")[:5000],
        status=IncidentStatus.DETECTED, created_by=user)
    IncidentEvent.objects.create(
        incident=incident, kind="detected", status=IncidentStatus.DETECTED,
        message=detail[:1000] or "Incident opened.", created_by=user)
    audit("incident.open", actor=user, organization=project.organization,
          target=f"incident:{incident.id}", summary=f"[{severity}] {title}")
    # Raise an operational alert (spec §21) — notifies the org, best-effort.
    try:
        from apps.notifications.alerts import raise_alert
        raise_alert(project, kind="incident", severity=severity, message=title)
    except Exception:
        pass
    return incident


def add_note(incident: Incident, text: str, *, user=None) -> IncidentEvent:
    text = (text or "").strip()
    if not text:
        raise IncidentError("A note can't be empty.")
    return IncidentEvent.objects.create(
        incident=incident, kind="note", message=text[:2000], created_by=user)


def transition(incident: Incident, status: str, *, user=None, note="") -> Incident:
    """Move the incident to a new status, recording it on the timeline. Resolving or
    closing stamps resolved_at. This is the only way the status changes."""
    if status not in IncidentStatus.values:
        raise IncidentError(f"Unknown status '{status}'.")
    if status == incident.status and not note:
        return incident
    incident.status = status
    fields = ["status", "updated_at"]
    if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and not incident.resolved_at:
        incident.resolved_at = timezone.now()
        fields.append("resolved_at")
    elif status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
        # Reopened — clear the resolution timestamp so duration stays honest.
        if incident.resolved_at:
            incident.resolved_at = None
            fields.append("resolved_at")
    incident.save(update_fields=fields)
    IncidentEvent.objects.create(
        incident=incident, kind="status", status=status,
        message=(note or "").strip()[:2000], created_by=user)
    audit("incident.transition", actor=user, organization=incident.project.organization,
          target=f"incident:{incident.id}", summary=f"{incident.title} → {status}")
    return incident


def set_resolution(incident: Incident, *, resolution="", postmortem="", user=None) -> Incident:
    fields = []
    if resolution:
        incident.resolution = resolution[:5000]
        fields.append("resolution")
    if postmortem:
        incident.postmortem = postmortem[:5000]
        fields.append("postmortem")
    if fields:
        incident.save(update_fields=fields + ["updated_at"])
    return incident


# --- auto-detection from real signals ----------------------------------------
def auto_detect_from_deploy(deployment, *, user=None) -> Incident | None:
    """Open an incident when a deployment fails — unless one is already open for it.
    Real signal in, real incident out (never fabricated)."""
    from apps.deployments.models import DeploymentStatus
    if deployment.status != DeploymentStatus.FAILED:
        return None
    existing = Incident.objects.filter(deployment=deployment).filter(
        status__in=(IncidentStatus.DETECTED, IncidentStatus.INVESTIGATING,
                    IncidentStatus.IDENTIFIED, IncidentStatus.MITIGATING)).first()
    if existing:
        return existing
    sev = "high" if deployment.is_production else "medium"
    return open_incident(
        deployment.project,
        title=f"Deployment to {deployment.environment} failed",
        severity=sev, source="deploy", deployment=deployment,
        detail=(deployment.log or "")[:2000] if hasattr(deployment, "log") else "",
        user=user)


# --- AI analysis (never changes status) --------------------------------------
def analyze(incident: Incident, *, user=None) -> IncidentEvent:
    """Record an analysis note for the incident. Deterministic summary of what's
    known; it NEVER resolves the incident (spec §20)."""
    parts = [f"Severity {incident.get_severity_display()}, status {incident.get_status_display()}."]
    if incident.deployment_id:
        parts.append(f"Linked to a {incident.deployment.environment} deployment.")
    if incident.detail:
        first = incident.detail.strip().splitlines()[0][:200]
        parts.append(f"Observed: {first}")
    parts.append("This is analysis only — the incident stays open until a person resolves it.")
    return IncidentEvent.objects.create(
        incident=incident, kind="analysis", message=" ".join(parts), created_by=user)


# --- queries -----------------------------------------------------------------
def open_incidents(project):
    return project.incidents.filter(status__in=(
        IncidentStatus.DETECTED, IncidentStatus.INVESTIGATING,
        IncidentStatus.IDENTIFIED, IncidentStatus.MITIGATING))


def summary(project) -> dict:
    incidents = list(project.incidents.all())
    openq = [i for i in incidents if i.is_open]
    return {
        "total": len(incidents),
        "open": len(openq),
        "critical_open": sum(1 for i in openq if i.severity == "critical"),
    }
