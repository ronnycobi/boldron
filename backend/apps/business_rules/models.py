"""Formal business rules (spec §12-13).

A business rule is a named policy the app enforces — "orders over R1000 ship
free", "VAT is 15%", "a quote over R50 000 needs manager approval". Today these
live only as free-text notes in project memory; this makes them first-class,
categorised, versioned records with an explicit lifecycle.

Honesty (CLAUDE.md — money/stock/auth logic is deterministic and lives in the
engine, never improvised): a rule is only reported as *enforceable* when it
carries a machine-evaluable `definition` the engine can actually decide. Rules
without one are *documented* — a recorded policy, honestly flagged as not
automatically enforced — never dressed up as if the system applied them.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class RuleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class RuleCategory(models.TextChoices):
    PRICING = "pricing", "Pricing"
    DISCOUNT = "discount", "Discount"
    SHIPPING = "shipping", "Shipping"
    TAX = "tax", "Tax"
    ACCESS = "access", "Access control"
    VALIDATION = "validation", "Validation"
    WORKFLOW = "workflow", "Workflow / approval"
    OTHER = "other", "Other"


class BusinessRule(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="business_rules",
    )
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=16, choices=RuleCategory.choices, default=RuleCategory.OTHER)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=RuleStatus.choices, default=RuleStatus.DRAFT)
    # Machine-evaluable definition {"when": [{fact, op, value}], "then": {outcome, ...}}.
    # Empty => documentation-only (not automatically enforced).
    definition = models.JSONField(default=dict, blank=True)
    # The requirement this rule supports, when it came from / belongs to one.
    requirement = models.ForeignKey(
        "project_context.ContextEntry", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="business_rules",
    )
    priority = models.IntegerField(default=100)
    source = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="authored_rules",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "name", "id"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"[{self.status}] {self.name}"

    @property
    def is_enforceable(self) -> bool:
        """True when the rule carries a definition the engine can evaluate."""
        from apps.business_rules.engine import validate_definition
        return bool(self.definition) and validate_definition(self.definition)[0]

    @property
    def is_active(self) -> bool:
        return self.status == RuleStatus.ACTIVE
