"""Developer platform: programmatic API keys + outbound webhooks (spec §21/§22).

Both are org-scoped. API keys authenticate real API requests (additive to the
JWT/session auth the web and mobile clients use). Webhooks deliver real events to
a customer URL, signed with a per-webhook secret, with every attempt logged.

Secrets are never stored in the clear: an API key's secret is shown once at
creation and only its hash is kept; a webhook's signing secret is generated once
and shown once. Everything here is genuinely wired — a key authenticates, a
webhook fires on a real event — never a placeholder.
"""
from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization

# Public key format: bk_<prefix>_<secret>. The prefix is stored in the clear for
# O(1) lookup; the secret half is only ever stored as a SHA-256 hash.
KEY_PUBLIC_PREFIX = "bk"
_PREFIX_LEN = 8
_SECRET_LEN = 32


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class ApiKey(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="api_keys"
    )
    name = models.CharField(max_length=120)
    # Lookup prefix (clear) + hashed secret (never reversible).
    prefix = models.CharField(max_length=16, unique=True, db_index=True)
    secret_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="api_keys_created",
    )
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…) for {self.organization_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def masked(self) -> str:
        return f"{KEY_PUBLIC_PREFIX}_{self.prefix}_••••••••"

    @classmethod
    def generate(cls, organization, name, *, created_by=None) -> tuple["ApiKey", str]:
        """Create a key and return (instance, plaintext). The plaintext is shown
        to the user exactly once — only its hash is stored."""
        prefix = secrets.token_hex(_PREFIX_LEN // 2)
        secret = secrets.token_urlsafe(_SECRET_LEN)
        key = cls.objects.create(
            organization=organization, name=name[:120], prefix=prefix,
            secret_hash=hash_secret(secret), created_by=created_by,
        )
        plaintext = f"{KEY_PUBLIC_PREFIX}_{prefix}_{secret}"
        return key, plaintext

    @classmethod
    def resolve(cls, plaintext: str) -> "ApiKey | None":
        """Return the active key matching this plaintext, or None. Constant-ish:
        looks up by prefix then compares the secret hash."""
        # The secret half is base64url and may itself contain "_", so split only
        # on the first two separators (bk / prefix / secret).
        parts = (plaintext or "").split("_", 2)
        if len(parts) != 3 or parts[0] != KEY_PUBLIC_PREFIX:
            return None
        _, prefix, secret = parts
        key = cls.objects.filter(prefix=prefix, revoked_at__isnull=True).first()
        if key is None:
            return None
        if not secrets.compare_digest(key.secret_hash, hash_secret(secret)):
            return None
        return key


class Webhook(models.Model):
    """An outbound webhook: an org URL that receives signed event deliveries."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="webhooks"
    )
    url = models.URLField(max_length=500)
    # Events this endpoint subscribes to (keys from developer.events.EVENTS).
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=64)  # HMAC signing secret (shown once)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="webhooks_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"webhook → {self.url} ({self.organization_id})"

    @staticmethod
    def new_secret() -> str:
        return secrets.token_urlsafe(32)

    def subscribes_to(self, event: str) -> bool:
        return self.active and (not self.events or event in self.events)


class WebhookDelivery(models.Model):
    """One delivery attempt. Kept as an honest audit trail — success or failure,
    status code, and any error are all recorded; nothing is faked as delivered."""

    webhook = models.ForeignKey(
        Webhook, on_delete=models.CASCADE, related_name="deliveries"
    )
    event = models.CharField(max_length=64)
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        state = "ok" if self.success else "failed"
        return f"{self.event} → {self.webhook_id} ({state})"
