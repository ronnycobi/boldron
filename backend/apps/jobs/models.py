"""Background jobs (spec §20) — long-running work that runs off the request
thread, with status that reflects reality.

A job only reaches COMPLETED when its handler genuinely returns, and FAILED (with
the real error) when it raises — never an optimistic "done". Progress is updated
by the handler as it works. This is a real executor (a worker thread per job,
matching how the build pipeline already runs); it is not a distributed queue, so
the capability is described honestly as "async work", not "infinitely scalable
infrastructure".
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization


class Job(models.Model):
    QUEUED, RUNNING, COMPLETED, FAILED = "queued", "running", "completed", "failed"
    STATUS = [(QUEUED, "Queued"), (RUNNING, "Running"),
              (COMPLETED, "Completed"), (FAILED, "Failed")]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="jobs")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, null=True, blank=True,
        related_name="jobs")
    kind = models.CharField(max_length=48)          # a registered handler key
    label = models.CharField(max_length=160)        # friendly description
    status = models.CharField(max_length=12, choices=STATUS, default=QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)  # 0–100
    params = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)     # set on success
    error = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="jobs_created")
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self):
        return f"{self.kind} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in (self.COMPLETED, self.FAILED)

    def set_progress(self, pct: int) -> None:
        self.progress = max(0, min(100, int(pct)))
        self.save(update_fields=["progress"])
