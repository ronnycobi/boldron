"""Trust Center (spec §26, §29) — the subprocessor register and inbound
vulnerability reports.

The subprocessor register is a factual list of the third parties that process
data to run the service; it must reflect the ACTUAL providers (no placeholders).
Vulnerability reports are received privately and never published.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class Subprocessor(models.Model):
    class Category(models.TextChoices):
        AI = "ai", "AI provider"
        PAYMENT = "payment", "Payment provider"
        EMAIL = "email", "Email provider"
        CLOUD = "cloud", "Cloud / hosting"
        ANALYTICS = "analytics", "Analytics"
        STORAGE = "storage", "Storage"
        AUTH = "auth", "Authentication"
        MONITORING = "monitoring", "Monitoring"
        ERROR_TRACKING = "error_tracking", "Error tracking"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING_REVIEW = "pending_review", "Pending review"
        REMOVED = "removed", "Removed"

    name = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=Category.choices,
                                default=Category.OTHER)
    service = models.CharField(max_length=200, blank=True)
    data_processed = models.CharField(max_length=300, blank=True)
    purpose = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=120, blank=True)
    transfer_mechanism = models.CharField(max_length=160, blank=True)
    security_notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices,
                              default=Status.ACTIVE)
    effective_date = models.DateField(null=True, blank=True)
    last_reviewed = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.category})"


class VulnerabilityReport(models.Model):
    """A responsible-disclosure submission (spec §29). Private — never published."""
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        TRIAGING = "triaging", "Triaging"
        CONFIRMED = "confirmed", "Confirmed"
        FIXED = "fixed", "Fixed"
        DUPLICATE = "duplicate", "Duplicate"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    reporter_email = models.EmailField(blank=True)
    summary = models.CharField(max_length=300)
    details = models.TextField(blank=True)
    severity_estimate = models.CharField(max_length=10, blank=True)   # low/medium/high/critical
    status = models.CharField(max_length=16, choices=Status.choices,
                              default=Status.RECEIVED)
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"vuln({self.summary[:40]})"


class SecurityIncident(models.Model):
    """A security incident (spec §30), distinct from operational incidents.

    The workflow is detection → classification → investigation → containment →
    remediation → resolution, with a post-incident review. Breach NOTIFICATION is
    never automatic: it is assessed and then an explicit action, so legal/security
    can review before anyone is told."""
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        DETECTED = "detected", "Detected"
        INVESTIGATING = "investigating", "Investigating"
        CONTAINED = "contained", "Contained"
        REMEDIATING = "remediating", "Remediating"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices,
                                default=Severity.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices,
                              default=Status.DETECTED)
    investigation = models.TextField(blank=True)
    containment = models.TextField(blank=True)
    remediation = models.TextField(blank=True)
    postmortem = models.TextField(blank=True)

    # Notification assessment — explicit, never automatic.
    notification_assessed = models.BooleanField(default=False)
    notification_required = models.BooleanField(default=False)
    notification_note = models.TextField(blank=True)
    notification_sent = models.BooleanField(default=False)

    detected_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at", "-id"]

    def __str__(self):
        return f"sec-incident({self.severity}, {self.status})"
