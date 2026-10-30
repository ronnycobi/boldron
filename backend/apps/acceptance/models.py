"""Acceptance criteria (spec §3) — first-class, trackable, verifiable records.

A requirement is only "done" when its acceptance criteria are genuinely met. The
Requirements Agent already extracts criteria as text embedded in each requirement;
this promotes them into standalone records that carry an HONEST status.

The honesty rule (same shape as incidents §20): a criterion starts `pending` and
only a person moves it to met / not-met / waived — the AI may draft and recommend
but never marks a criterion met. "Met" always carries who verified it and when, so
the platform never claims acceptance it cannot evidence.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class CriterionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    MET = "met", "Met"
    FAILED = "failed", "Not met"
    WAIVED = "waived", "Waived"


# Statuses that represent a deliberate human verification decision.
VERIFIED_STATUSES = {CriterionStatus.MET, CriterionStatus.FAILED, CriterionStatus.WAIVED}


class AcceptanceCriterion(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="acceptance_criteria",
    )
    # The requirement this criterion belongs to, when it came from one. Kept as a
    # nullable link so deleting a requirement doesn't erase its verification record.
    requirement = models.ForeignKey(
        "project_context.ContextEntry", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="acceptance_criteria",
    )
    statement = models.TextField()
    status = models.CharField(
        max_length=16, choices=CriterionStatus.choices,
        default=CriterionStatus.PENDING,
    )
    # Verification provenance — only set when a person verifies the criterion.
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="verified_criteria",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    source = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["requirement_id", "order", "id"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"[{self.status}] {self.statement[:60]}"

    @property
    def is_met(self) -> bool:
        return self.status == CriterionStatus.MET

    @property
    def requirement_title(self) -> str:
        return self.requirement.title if self.requirement_id else ""
