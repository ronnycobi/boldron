"""Feature flags (spec §19).

A flag turns part of an app on or off without a redeploy. Each flag belongs to a
project and is evaluated deterministically: it's off unless enabled, and an
enabled flag can be rolled out to a percentage of subjects and/or gated on
targeting conditions (evaluated by the shared business-rules engine).

Honesty: a flag reports only its real state. A percentage rollout buckets a
subject with a stable hash, so the same subject always gets the same answer —
there is no fabricated "on", and no flag is reported enabled that the engine
wouldn't actually enable.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class FeatureFlag(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="feature_flags")
    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    # Percentage of subjects the flag is on for when enabled (100 = everyone).
    rollout = models.PositiveSmallIntegerField(default=100)
    # Optional targeting: a business-rules `when` list [{fact, op, value}] (AND).
    conditions = models.JSONField(default=list, blank=True)
    archived = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_flags")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "key"],
                                    name="unique_flag_per_project")
        ]
        indexes = [models.Index(fields=["project", "archived"])]

    def __str__(self):
        return f"{self.key} ({'on' if self.enabled else 'off'})"

    @property
    def is_targeted(self) -> bool:
        return bool(self.conditions) or self.rollout < 100
