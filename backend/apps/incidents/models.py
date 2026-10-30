"""Incident management (spec §20).

A first-class operational incident with a real lifecycle, a timeline of events, the
affected project/deployment, and resolution + post-incident notes. Incidents can be
opened manually or auto-detected from real signals (a failed deployment). The AI may
analyse an incident, but it NEVER marks one resolved — moving to 'resolved'/'closed'
is always an explicit human action (spec §20).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class IncidentSeverity(models.TextChoices):
    CRITICAL = "critical", "Critical"     # outage / data at risk
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class IncidentStatus(models.TextChoices):
    DETECTED = "detected", "Detected"
    INVESTIGATING = "investigating", "Investigating"
    IDENTIFIED = "identified", "Identified"
    MITIGATING = "mitigating", "Mitigating"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


# The forward lifecycle order; a status can also stay or reopen (resolved -> investigating).
_OPEN_STATUSES = {
    IncidentStatus.DETECTED, IncidentStatus.INVESTIGATING,
    IncidentStatus.IDENTIFIED, IncidentStatus.MITIGATING,
}


class Incident(models.Model):
    SOURCES = [("manual", "Manual"), ("deploy", "Deployment"), ("monitoring", "Monitoring")]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="incidents")
    deployment = models.ForeignKey(
        "deployments.Deployment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incidents")
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=10, choices=IncidentSeverity.choices,
                                default=IncidentSeverity.MEDIUM)
    status = models.CharField(max_length=14, choices=IncidentStatus.choices,
                              default=IncidentStatus.DETECTED)
    source = models.CharField(max_length=12, choices=SOURCES, default="manual")
    detail = models.TextField(blank=True)          # error info / what was observed
    resolution = models.TextField(blank=True)      # how it was resolved
    postmortem = models.TextField(blank=True)      # post-incident notes
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="opened_incidents")
    detected_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in _OPEN_STATUSES

    @property
    def duration_seconds(self) -> int | None:
        if self.resolved_at:
            return int((self.resolved_at - self.detected_at).total_seconds())
        return None


class IncidentEvent(models.Model):
    """One entry on an incident's timeline — a detection, a status change, or a note."""

    KINDS = [("detected", "Detected"), ("status", "Status change"),
             ("note", "Note"), ("analysis", "Analysis")]

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=KINDS, default="note")
    status = models.CharField(max_length=14, blank=True)   # status at this event (for 'status')
    message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incident_events")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.kind} @ {self.created_at:%Y-%m-%d %H:%M}"
