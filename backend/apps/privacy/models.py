"""Privacy rights & requests (spec §17-19).

A structured, auditable workflow for data-subject requests. The exact rights that
apply depend on the user's jurisdiction and the applicable law — the engine records
the request and its lifecycle but makes no legal determination on its own. Deletion
is never an instant irreversible wipe: it is a tracked request a human actions,
with ownership/organization handling considered first.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class RequestType(models.TextChoices):
    ACCESS = "access", "Access my data"
    EXPORT = "export", "Export my data"
    CORRECTION = "correction", "Correct my data"
    DELETION = "deletion", "Delete my data"
    RESTRICTION = "restriction", "Restrict processing"
    OBJECTION = "objection", "Object to processing"
    PORTABILITY = "portability", "Data portability"
    CONSENT_WITHDRAWAL = "consent_withdrawal", "Withdraw consent"


class RequestStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    VERIFYING = "verifying", "Verifying identity"
    VERIFIED = "verified", "Verified"
    IN_PROGRESS = "in_progress", "In progress"
    WAITING = "waiting", "Waiting on requester"
    COMPLETED = "completed", "Completed"
    PARTIALLY_COMPLETED = "partially_completed", "Partially completed"
    REJECTED = "rejected", "Rejected"


OPEN_STATUSES = {
    RequestStatus.RECEIVED, RequestStatus.VERIFYING, RequestStatus.VERIFIED,
    RequestStatus.IN_PROGRESS, RequestStatus.WAITING,
}


class PrivacyRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="privacy_requests")
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="privacy_requests")
    request_type = models.CharField(max_length=24, choices=RequestType.choices)
    jurisdiction = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=24, choices=RequestStatus.choices,
                              default=RequestStatus.RECEIVED)
    details = models.TextField(blank=True)
    identity_verified = models.BooleanField(default=False)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_privacy_requests")
    deadline = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "status"]),
                   models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.request_type} by {self.user_id} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class PrivacyRequestEvent(models.Model):
    request = models.ForeignKey(
        PrivacyRequest, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=24)      # submitted/status/note/assigned
    status = models.CharField(max_length=24, blank=True)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.kind} {self.status}"
