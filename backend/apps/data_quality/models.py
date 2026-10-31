"""Data quality (spec §9) — rules a dataset's data must satisfy, and the real
results of checking them.

A dataset is a logical table in the app (customers, orders…). Its rules are
deterministic checks; a check run records the true outcome against the rows it was
given, so the quality score and the issues list are always real, never estimated.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Dataset(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="datasets")
    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["key", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "key"],
                                    name="unique_dataset_per_project")
        ]

    def __str__(self):
        return self.key


class DataQualityRule(models.Model):
    class Severity(models.TextChoices):
        ERROR = "error", "Error"
        WARNING = "warning", "Warning"

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="rules")
    field = models.CharField(max_length=120)
    check_type = models.CharField(max_length=32)
    params = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=8, choices=Severity.choices,
                                default=Severity.ERROR)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["field", "id"]

    def __str__(self):
        return f"{self.field}:{self.check_type}"


class DataQualityRun(models.Model):
    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="runs")
    rows = models.PositiveIntegerField(default=0)
    score = models.IntegerField(null=True, blank=True)
    failing = models.PositiveIntegerField(default=0)
    results = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Run {self.dataset_id} score={self.score}"
