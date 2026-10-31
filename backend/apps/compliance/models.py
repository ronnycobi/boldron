"""Compliance (spec §16).

A project tracks compliance controls grouped by framework (data protection,
accessibility, security…). Each control has an honest status that a person
attests with evidence — the platform never claims a project is "compliant".

Some controls are genuinely provided by the platform (data export, an audit
trail, role-based access); those are evidenced automatically from real facts and
marked as platform-provided. Everything else starts pending and only a person,
with evidence, moves it to met — so the compliance picture is always truthful.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Framework(models.TextChoices):
    GDPR = "gdpr", "GDPR (EU data protection)"
    POPIA = "popia", "POPIA (South Africa)"
    ACCESSIBILITY = "accessibility", "Accessibility (WCAG)"
    SECURITY = "security", "Security baseline"


class ControlStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    MET = "met", "Met"
    PARTIAL = "partial", "Partial"
    NOT_MET = "not_met", "Not met"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class ComplianceControl(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="compliance_controls")
    framework = models.CharField(max_length=24, choices=Framework.choices)
    code = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=ControlStatus.choices,
                              default=ControlStatus.PENDING)
    evidence = models.TextField(blank=True)
    # True when the status is evidenced automatically from a real platform fact.
    auto = models.BooleanField(default=False)
    attested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="attested_controls")
    attested_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["framework", "code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "framework", "code"],
                                    name="unique_control_per_project")
        ]
        indexes = [models.Index(fields=["project", "framework"])]

    def __str__(self):
        return f"[{self.framework}:{self.status}] {self.code}"
