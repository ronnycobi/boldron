"""Account lifecycle & appeals (spec §42-43).

An account (organization) moves through active → restricted → suspended →
terminated. Each change is an append-only AccountAction recording WHY: the reason,
the policy section, the reviewer and any evidence — never an arbitrary silent ban.
A customer can appeal, and the appeal has its own reviewed outcome.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RESTRICTED = "restricted", "Restricted"
    SUSPENDED = "suspended", "Suspended"
    TERMINATED = "terminated", "Terminated"


# Statuses that block using the service (restricted still works, just flagged).
BLOCKED_STATUSES = {AccountStatus.SUSPENDED, AccountStatus.TERMINATED}


class AccountState(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE,
        related_name="account_state")
    status = models.CharField(max_length=16, choices=AccountStatus.choices,
                              default=AccountStatus.ACTIVE)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization_id}:{self.status}"


class AccountAction(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE,
        related_name="account_actions")
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    reason = models.TextField(blank=True)
    policy_section = models.CharField(max_length=120, blank=True)
    evidence = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="account_actions")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.organization_id}: {self.from_status}->{self.to_status}"


class Appeal(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEWING = "reviewing", "Reviewing"
        DECIDED = "decided", "Decided"

    class Outcome(models.TextChoices):
        UPHELD = "upheld", "Upheld"
        REVERSED = "reversed", "Reversed"
        MODIFIED = "modified", "Modified"
        WARNING = "warning", "Warning"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="appeals")
    action = models.ForeignKey(
        AccountAction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="appeals")
    reason = models.TextField()
    evidence = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="appeals")
    status = models.CharField(max_length=12, choices=Status.choices,
                              default=Status.SUBMITTED)
    outcome = models.CharField(max_length=12, choices=Outcome.choices, blank=True)
    resolution = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_appeals")
    created_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"appeal({self.organization_id}, {self.status})"
