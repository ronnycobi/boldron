"""Security-scan ledger (spec §8).

A persistent record of every security scan of a project's code, with its REAL
findings (from apps.security.scanner, which runs offline and never fabricates), so a
customer has scan history and the platform can gate a production deploy on there
being no high-severity findings.

Honesty: status is derived from the real scan. "skipped" means there was no code to
scan — it is NOT "clean", and nothing is marked safe that wasn't actually scanned.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SecurityScanStatus(models.TextChoices):
    CLEAN = "clean", "No findings"
    FINDINGS = "findings", "Findings (non-blocking)"   # medium/low only
    BLOCKED = "blocked", "High-severity findings"       # at least one HIGH — blocks deploy
    SKIPPED = "skipped", "Skipped"                       # no code to scan
    ERROR = "error", "Error"


class SecurityScan(models.Model):
    TRIGGERS = [
        ("manual", "Manual"),
        ("change", "Change"),
        ("pre_deploy", "Before deploy"),
    ]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="security_scans")
    trigger = models.CharField(max_length=16, choices=TRIGGERS, default="manual")
    status = models.CharField(max_length=10, choices=SecurityScanStatus.choices,
                              default=SecurityScanStatus.SKIPPED)
    high = models.PositiveIntegerField(default=0)
    medium = models.PositiveIntegerField(default=0)
    low = models.PositiveIntegerField(default=0)
    files_scanned = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="security_scans")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self):
        return f"SecurityScan {self.project_id} {self.status} (H{self.high}/M{self.medium}/L{self.low})"

    @property
    def total(self) -> int:
        return self.high + self.medium + self.low

    @property
    def blocks_deploy(self) -> bool:
        return self.status == SecurityScanStatus.BLOCKED

    @property
    def summary(self) -> str:
        if self.status == SecurityScanStatus.SKIPPED:
            return self.note or "no code to scan"
        if self.status == SecurityScanStatus.ERROR:
            return self.note or "the scan could not complete"
        if self.total == 0:
            return f"scanned {self.files_scanned} file(s), no findings"
        return f"{self.high} high · {self.medium} medium · {self.low} low"


class SecurityFinding(models.Model):
    scan = models.ForeignKey(SecurityScan, on_delete=models.CASCADE, related_name="findings")
    severity = models.CharField(max_length=8)   # high / medium / low
    category = models.CharField(max_length=40)
    message = models.CharField(max_length=300)
    path = models.CharField(max_length=500)
    line = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{self.severity}] {self.message} ({self.path}:{self.line})"
