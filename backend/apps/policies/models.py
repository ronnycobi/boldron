"""Policy engine (spec §44) — declarative governance over platform actions.

A policy is a guardrail on a platform action (today: deploys). It matches an
action's context with the shared business-rules condition engine and carries an
effect — block, require approval, or warn. Policies are consulted at the real
decision point (the deploy pre-flight), so a block policy genuinely prevents the
action; nothing here is advisory-only unless its effect is `warn`.

Honesty: a policy can only be created for a scope the platform actually enforces,
so there are no inert policies that look like governance but do nothing. The
platform's own built-in guardrails (production approval, the high-severity
security block) are surfaced read-only alongside custom policies so the full
governance picture is truthful.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PolicyScope(models.TextChoices):
    DEPLOY = "deploy", "Deploy"


class PolicyEffect(models.TextChoices):
    BLOCK = "block", "Block"
    REQUIRE_APPROVAL = "require_approval", "Require approval"
    WARN = "warn", "Warn"


class Policy(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="policies")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=24, choices=PolicyScope.choices,
                             default=PolicyScope.DEPLOY)
    effect = models.CharField(max_length=24, choices=PolicyEffect.choices,
                              default=PolicyEffect.BLOCK)
    # A business-rules `when` list [{fact, op, value}] (AND); empty = always applies.
    conditions = models.JSONField(default=list, blank=True)
    message = models.CharField(max_length=300, blank=True)
    enabled = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="authored_policies")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "name", "id"]
        indexes = [models.Index(fields=["project", "scope", "enabled"])]

    def __str__(self):
        return f"[{self.scope}:{self.effect}] {self.name}"

    @property
    def reason(self) -> str:
        return self.message or self.name
