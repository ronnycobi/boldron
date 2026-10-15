"""Per-user notification preferences.

Only categories that map to a real, optional email appear here — toggling one
genuinely suppresses mail that would otherwise be sent. Essential/transactional
mail (email verification, password reset, organization invitations) is never
gated by a preference and is intentionally absent from this model.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


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
