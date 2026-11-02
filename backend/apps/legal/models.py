"""The Legal & Compliance engine — versioned documents + durable acceptance (§1-4).

Two keystone models everything else hangs off:

  LegalDocument  — a single, immutable published version of one legal document
                   for one jurisdiction + language. Publishing freezes the content
                   and its hash; a change is a NEW version row, never an overwrite.

  LegalAcceptance — a durable record that a user agreed to a SPECIFIC document
                    version: document, version, content hash, when, who, org, IP /
                    user-agent / country where captured, consent type, whether it
                    was mandatory, and the method. Never a boolean flag on the user.
"""
from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone


def content_hash(text: str) -> str:
    """Stable SHA-256 of a document's content — the fingerprint an acceptance pins."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    UNDER_REVIEW = "under_review", "Under review"
    APPROVED = "approved", "Approved"
    SCHEDULED = "scheduled", "Scheduled"
    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"
    ARCHIVED = "archived", "Archived"


# Statuses whose content is frozen — never editable again.
FROZEN_STATUSES = {DocumentStatus.PUBLISHED, DocumentStatus.SUPERSEDED,
                   DocumentStatus.ARCHIVED}


class LegalDocument(models.Model):
    document_type = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=160, unique=True)
    jurisdiction = models.CharField(max_length=40, default="global")
    language = models.CharField(max_length=15, default="en")
    version = models.CharField(max_length=20)            # e.g. "1.0", "2.1"
    status = models.CharField(max_length=16, choices=DocumentStatus.choices,
                              default=DocumentStatus.DRAFT)

    content = models.TextField(blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)

    effective_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    requires_acceptance = models.BooleanField(default=False)
    # Who must accept: "user" (each person) or "organization" (an owner, once).
    acceptance_scope = models.CharField(max_length=16, default="user")
    change_summary = models.TextField(blank=True)

    # The version this one supersedes (for an auditable chain).
    supersedes = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="superseded_by")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="authored_legal_documents")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_legal_documents")
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type", "jurisdiction", "-published_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "jurisdiction", "language", "version"],
                name="unique_legal_version"),
        ]
        indexes = [
            models.Index(fields=["document_type", "jurisdiction", "status"]),
        ]

    def __str__(self):
        return f"{self.document_type} {self.version} ({self.status})"

    @property
    def is_published(self) -> bool:
        return self.status == DocumentStatus.PUBLISHED

    @property
    def is_frozen(self) -> bool:
        return self.status in FROZEN_STATUSES

    def save(self, *args, **kwargs):
        # Immutability guard: once frozen, content + identity can never change.
        if self.pk:
            try:
                prior = LegalDocument.objects.get(pk=self.pk)
            except LegalDocument.DoesNotExist:
                prior = None
            if prior and prior.status in FROZEN_STATUSES:
                for field in ("content", "content_sha256", "version",
                              "document_type", "jurisdiction", "language"):
                    if getattr(self, field) != getattr(prior, field):
                        raise ValueError(
                            "A published legal document is immutable; publish a new "
                            "version instead of editing this one.")
        super().save(*args, **kwargs)


class ConsentType(models.TextChoices):
    MANDATORY = "mandatory", "Mandatory"      # required to use the service
    OPTIONAL = "optional", "Optional"          # offered, not required
    MARKETING = "marketing", "Marketing"       # separate marketing consent


class LegalAcceptance(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="legal_acceptances")
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE,
        null=True, blank=True, related_name="legal_acceptances")
    document = models.ForeignKey(
        LegalDocument, on_delete=models.PROTECT, related_name="acceptances")

    # Denormalised so the record stands on its own, immutably, forever.
    document_type = models.CharField(max_length=60)
    version = models.CharField(max_length=20)
    content_sha256 = models.CharField(max_length=64)

    consent_type = models.CharField(max_length=16, choices=ConsentType.choices,
                                    default=ConsentType.MANDATORY)
    mandatory = models.BooleanField(default=True)
    method = models.CharField(max_length=32, default="clickwrap")

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    country = models.CharField(max_length=40, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    accepted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-accepted_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "document"],
                                    name="unique_acceptance_per_user_version"),
        ]
        indexes = [models.Index(fields=["user", "document_type"])]

    def __str__(self):
        return f"{self.user_id} accepted {self.document_type} {self.version}"
