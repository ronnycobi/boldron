"""Test-run ledger (spec §8).

A persistent record of every time a project's test suite was actually run, with its
REAL outcome (counts + pass/fail from the sandbox process), so a customer has test
history and the platform can gate a production deploy on tests genuinely passing.

Honesty: status is derived from a real run (apps.codegen.run_repo_tests), never
fabricated. "skipped" means there was nothing runnable to test (no repo, or a stack
the sandbox can't run) — it is NOT "passed", and the deploy gate treats it as such.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class TestRunStatus(models.TextChoices):
    RUNNING = "running", "Running"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"        # nothing runnable — never treated as passed
    ERROR = "error", "Error"              # the run itself failed to execute


class TestRun(models.Model):
    TRIGGERS = [
        ("manual", "Manual"),
        ("change", "Change"),
        ("pre_deploy", "Before deploy"),
    ]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="test_runs")
    change = models.ForeignKey(
        "changes.ChangeRequest", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="test_runs")
    trigger = models.CharField(max_length=16, choices=TRIGGERS, default="manual")
    status = models.CharField(max_length=10, choices=TestRunStatus.choices,
                              default=TestRunStatus.RUNNING)
    ran = models.PositiveIntegerField(default=0)
    failures = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="test_runs")
    created_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self):
        return f"TestRun {self.project_id} {self.status} ({self.ran} ran)"

    @property
    def passed(self) -> bool:
        return self.status == TestRunStatus.PASSED

    @property
    def summary(self) -> str:
        if self.status == TestRunStatus.PASSED:
            return f"{self.ran} test(s) passed"
        if self.status == TestRunStatus.FAILED:
            return f"{self.failures} failure(s), {self.errors} error(s) of {self.ran}"
        if self.status == TestRunStatus.SKIPPED:
            return self.note or "nothing to test"
        if self.status == TestRunStatus.ERROR:
            return self.note or "the test run could not complete"
        return "running…"
