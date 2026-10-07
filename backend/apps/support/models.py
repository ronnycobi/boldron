"""Support center — tickets customers log and staff work (help desk).

A customer raises a SupportTicket (a question, bug, billing issue, logged call, …);
it carries a threaded conversation of TicketMessages. Staff see every tenant's
tickets in the Control Center and reply; internal notes stay staff-only.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    WAITING = "waiting", "Waiting on customer"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


OPEN_STATUSES = ("open", "in_progress", "waiting")

# SLA targets in HOURS by priority: (first response, resolution). Tuned per
# priority so urgent issues carry tighter commitments than routine questions.
SLA_HOURS = {
    "urgent": (1, 8),
    "high": (4, 24),
    "normal": (8, 72),
    "low": (24, 120),
}


class SupportTicket(models.Model):
    CATEGORIES = [("question", "Question"), ("bug", "Problem / bug"),
                  ("billing", "Billing"), ("feature", "Feature request"),
                  ("call", "Logged call"), ("other", "Other")]
    PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="support_tickets"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="support_tickets",
    )
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=16, choices=CATEGORIES, default="question")
    priority = models.CharField(max_length=8, choices=PRIORITIES, default="normal")
    status = models.CharField(max_length=16, choices=TicketStatus.choices, default=TicketStatus.OPEN)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_tickets",
    )
    # SLA clock — targets are stamped on create from the priority; first_responded_at
    # is set the first time staff reply publicly. Breach is derived (see properties).
    first_response_due = models.DateTimeField(null=True, blank=True)
    resolution_due = models.DateTimeField(null=True, blank=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.number} {self.subject}"

    @property
    def number(self) -> str:
        prefix = getattr(settings, "APP_TICKET_PREFIX", "TKT")
        return f"{prefix}-{self.pk:05d}"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def apply_sla(self) -> None:
        """Stamp first-response and resolution targets from the current priority."""
        resp_h, res_h = SLA_HOURS.get(self.priority, SLA_HOURS["normal"])
        base = self.created_at or timezone.now()
        self.first_response_due = base + timedelta(hours=resp_h)
        self.resolution_due = base + timedelta(hours=res_h)

    @property
    def response_overdue(self) -> bool:
        # Overdue only while still unanswered.
        return bool(
            self.first_response_due
            and self.first_responded_at is None
            and not self._is_done()
            and timezone.now() > self.first_response_due
        )

    @property
    def resolution_overdue(self) -> bool:
        return bool(
            self.resolution_due
            and not self._is_done()
            and timezone.now() > self.resolution_due
        )

    def _is_done(self) -> bool:
        return self.status in ("resolved", "closed")

    @property
    def sla_state(self) -> str:
        """'breached' | 'at_risk' | 'ok' | 'met' — for a badge on the desk."""
        if self._is_done():
            return "met"
        if self.response_overdue or self.resolution_overdue:
            return "breached"
        # Within 25% of a deadline counts as at-risk.
        now = timezone.now()
        for due, done in ((self.first_response_due, self.first_responded_at),
                          (self.resolution_due, None)):
            if due and done is None:
                total = (due - (self.created_at or now)).total_seconds() or 1
                if 0 < (due - now).total_seconds() <= total * 0.25:
                    return "at_risk"
        return "ok"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ticket_messages",
    )
    body = models.TextField()
    internal = models.BooleanField(default=False)   # staff-only note; hidden from the customer
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"msg on {self.ticket_id}"
