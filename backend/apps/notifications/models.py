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
