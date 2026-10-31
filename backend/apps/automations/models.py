"""Automations (spec §10-11) — trigger → conditions → actions.

An automation reacts to a real platform event (its trigger), checks its
conditions against the event's facts (evaluated by the shared business-rules
engine), and runs its actions. Every execution is recorded as a WorkflowRun with
each action's HONEST outcome, so the history proves what actually happened —
including actions that were skipped because a capability isn't configured.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkflowStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"


class Workflow(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="automations")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger = models.CharField(max_length=48)
    # A business-rules `when`-style list: [{fact, op, value}] (AND); empty = always.
    conditions = models.JSONField(default=list, blank=True)
    # Ordered list of {type, params}.
    actions = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT)

    run_count = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="authored_automations")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["project", "trigger", "status"])]

    def __str__(self):
        return f"[{self.status}] {self.name}"

    @property
    def is_active(self) -> bool:
        return self.status == WorkflowStatus.ACTIVE


class RunStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"      # all actions done
    PARTIAL = "partial", "Partial"            # some skipped/failed
    FAILED = "failed", "Failed"               # every action failed
    SKER = "skipped", "Skipped"               # conditions didn't match / nothing ran


class WorkflowRun(models.Model):
    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="runs")
    trigger = models.CharField(max_length=48)
    facts = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=RunStatus.choices)
    # [{action, outcome, detail}] — one per action attempted.
    results = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Run {self.workflow_id} {self.status}"
