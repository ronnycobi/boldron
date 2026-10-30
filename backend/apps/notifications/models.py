"""Per-user notification preferences.

Only categories that map to a real, optional email appear here — toggling one
genuinely suppresses mail that would otherwise be sent. Essential/transactional
mail (email verification, password reset, organization invitations) is never
gated by a preference and is intentionally absent from this model.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    # Support ticket confirmations and staff replies (apps.support). Default on.
    support_updates = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"notification prefs for {self.user_id}"


class SmsMessage(models.Model):
    """A log of one SMS send attempt and its REAL outcome (spec §27). 'sent' is set
    only when a configured gateway actually accepted the message; with no provider
    connected the row is 'failed' with an honest reason — never a fake success."""

    STATUS = [("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")]

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE,
        related_name="sms_messages", null=True, blank=True)
    to = models.CharField(max_length=32)
    body = models.TextField()
    provider = models.CharField(max_length=32, blank=True)
    provider_ref = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default="queued")
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SMS to {self.to} ({self.status})"


class AlertPreference(models.Model):
    """Org-level alerting preference (spec §21). Operational alerts email the org's
    owners/admins by default; an org can turn that off here. Preference only — it
    never fakes or suppresses the underlying event, which is always recorded."""

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE,
        related_name="alert_preference")
    email_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"alerts for {self.organization_id} (email={self.email_enabled})"


class Alert(models.Model):
    """A persistent record of an operational alert raised for a project (spec §21).

    The Alert IS the in-app notification; `emailed` records whether a real email was
    actually dispatched to recipients. Push is not attempted (no provider connected),
    so it is honestly never reported as sent."""

    SEVERITIES = [("critical", "Critical"), ("high", "High"),
                  ("medium", "Medium"), ("low", "Low")]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=40)       # deploy_failed, incident, security, …
    severity = models.CharField(max_length=10, choices=SEVERITIES, default="medium")
    message = models.CharField(max_length=300)
    emailed = models.PositiveIntegerField(default=0)   # recipients the email reached
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self):
        return f"[{self.severity}] {self.kind}: {self.message[:40]}"
