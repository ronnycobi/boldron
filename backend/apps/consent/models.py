"""Consent management (spec §21-22, §45, §60).

Two separate, append-only consent logs — the latest record for a subject is their
current state, and history is never overwritten (an auditable trail of what was
agreed, when, under which policy version):

  CookieConsent   — per-category cookie/tracking consent. NECESSARY cookies are
                    always on (they make the service work); everything else is
                    off until the person opts in, and declining is a first-class
                    choice (no dark patterns).

  MarketingConsent — opt-IN consent for marketing communications, kept strictly
                     separate from service/transactional communications (which are
                     governed by NotificationPreference). Default is NOT opted in.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

# Optional categories (necessary is implicit and always allowed).
OPTIONAL_CATEGORIES = ["preferences", "analytics", "marketing"]


class CookieConsent(models.Model):
    # Either a logged-in user or a pre-login anonymous browser id.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name="cookie_consents")
    anon_id = models.CharField(max_length=64, blank=True)

    necessary = models.BooleanField(default=True)       # always true
    preferences = models.BooleanField(default=False)
    analytics = models.BooleanField(default=False)
    marketing = models.BooleanField(default=False)

    policy_version = models.CharField(max_length=20, blank=True)
    method = models.CharField(max_length=24, default="banner")
    jurisdiction = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["anon_id", "-created_at"]),
        ]

    def __str__(self):
        who = self.user_id or self.anon_id or "?"
        return f"cookie-consent({who})"

    def allowed(self, category: str) -> bool:
        if category == "necessary":
            return True
        return bool(getattr(self, category, False))


class MarketingConsent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="marketing_consents")
    opted_in = models.BooleanField(default=False)
    source = models.CharField(max_length=40, default="settings")
    policy_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"marketing({self.user_id}, {'in' if self.opted_in else 'out'})"
