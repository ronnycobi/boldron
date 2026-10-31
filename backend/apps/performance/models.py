"""Performance intelligence (spec §41).

The app records real timing samples (how long an endpoint, page or query took);
the platform turns them into honest percentiles, finds the slowest surfaces, and
flags anything over its performance budget. Everything is computed from recorded
measurements — no synthetic timings, and "no data yet" when nothing has been
measured.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class PerformanceSample(models.Model):
    class Kind(models.TextChoices):
        API = "api", "API"
        PAGE = "page", "Page"
        QUERY = "query", "Query"
        JOB = "job", "Job"
        OTHER = "other", "Other"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="perf_samples")
    label = models.CharField(max_length=200)        # e.g. "GET /orders"
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.API)
    duration_ms = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["project", "label", "recorded_at"])]

    def __str__(self):
        return f"{self.label} {self.duration_ms}ms"


class PerformanceBudget(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="perf_budgets")
    label = models.CharField(max_length=200)        # a label, or "*" for the default
    threshold_ms = models.PositiveIntegerField()    # the p95 budget
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(fields=["project", "label"],
                                    name="unique_budget_per_label")
        ]

    def __str__(self):
        return f"{self.label} <= {self.threshold_ms}ms"
