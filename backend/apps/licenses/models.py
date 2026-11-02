"""Dependency & license records for a project (spec §12)."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class Dependency(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="dependencies")
    package = models.CharField(max_length=200)
    version = models.CharField(max_length=60, blank=True)
    license = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=60, blank=True)      # pypi / npm / …
    dependency_type = models.CharField(max_length=16, default="runtime")  # runtime/dev
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["package", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "package"],
                                    name="unique_dependency_per_project")
        ]

    def __str__(self):
        return f"{self.package} {self.version}".strip()
