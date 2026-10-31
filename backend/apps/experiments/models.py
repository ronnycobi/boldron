"""A/B testing (spec §20).

An experiment splits subjects between variants and measures a conversion. Each
subject is assigned once, deterministically, and that assignment plus whether the
subject converted is the real data results are computed from.

Honesty: assignment is a stable weighted hash (the same subject always gets the
same variant), exposures and conversions are real recorded counts, and a winner
is only declared when a proper significance test on that real data says so —
otherwise the result is "not enough data", never a fabricated uplift.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExperimentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    RUNNING = "running", "Running"
    STOPPED = "stopped", "Stopped"


class Experiment(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="experiments")
    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=ExperimentStatus.choices,
                              default=ExperimentStatus.DRAFT)
    # [{key, name, weight}] — at least two, weights > 0.
    variants = models.JSONField(default=list)
    metric = models.CharField(max_length=120, default="conversion")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_experiments")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "key"],
                                    name="unique_experiment_per_project")
        ]

    def __str__(self):
        return f"[{self.status}] {self.key}"

    @property
    def is_running(self) -> bool:
        return self.status == ExperimentStatus.RUNNING


class Assignment(models.Model):
    experiment = models.ForeignKey(
        Experiment, on_delete=models.CASCADE, related_name="assignments")
    subject = models.CharField(max_length=200)
    variant = models.CharField(max_length=100)
    converted = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(default=timezone.now)
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["experiment", "subject"],
                                    name="unique_assignment_per_subject")
        ]
        indexes = [models.Index(fields=["experiment", "variant"])]

    def __str__(self):
        return f"{self.subject}->{self.variant}"
