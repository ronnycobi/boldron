"""Feature-flag lifecycle + deterministic evaluation (spec §19)."""
from __future__ import annotations

import hashlib

from django.db import IntegrityError

from apps.audit.service import record as audit
from apps.business_rules.engine import OPERATORS, match_conditions
from apps.flags.models import FeatureFlag


class FlagError(Exception):
    pass


def _validate_conditions(conditions):
    if not isinstance(conditions, list):
        raise FlagError("Targeting conditions must be a list.")
    for i, c in enumerate(conditions):
        if not isinstance(c, dict) or not str(c.get("fact", "")).strip():
            raise FlagError(f"Condition {i} needs a fact.")
        if c.get("op") not in OPERATORS:
            raise FlagError(f"Condition {i} has an unknown operator.")
        if "value" not in c:
            raise FlagError(f"Condition {i} needs a value.")


def _clamp_rollout(value) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise FlagError("Rollout must be a whole number 0-100.")
    if not 0 <= v <= 100:
        raise FlagError("Rollout must be between 0 and 100.")
    return v


def create(project, *, key, name="", description="", enabled=False, rollout=100,
           conditions=None, user=None) -> FeatureFlag:
    key = (key or "").strip().lower()
    if not key:
        raise FlagError("A flag needs a key.")
    conditions = conditions or []
    _validate_conditions(conditions)
    rollout = _clamp_rollout(rollout)
    try:
        flag = FeatureFlag.objects.create(
            project=project, key=key[:100], name=name.strip()[:200],
            description=(description or "").strip(), enabled=bool(enabled),
            rollout=rollout, conditions=conditions, created_by=user)
    except IntegrityError:
        raise FlagError(f"A flag with key '{key}' already exists.")
    audit("flag.create", actor=user, organization=project.organization,
          target=f"flag:{flag.id}", summary=f"{key} ({'on' if enabled else 'off'})")
    return flag


def update(flag: FeatureFlag, *, user=None, **fields) -> FeatureFlag:
    if "name" in fields:
        flag.name = (fields["name"] or "").strip()[:200]
    if "description" in fields:
        flag.description = (fields["description"] or "").strip()
    if "enabled" in fields:
        flag.enabled = bool(fields["enabled"])
    if "rollout" in fields:
        flag.rollout = _clamp_rollout(fields["rollout"])
    if "conditions" in fields:
        _validate_conditions(fields["conditions"] or [])
        flag.conditions = fields["conditions"] or []
    if "archived" in fields:
        flag.archived = bool(fields["archived"])
    flag.save()
    audit("flag.update", actor=user, organization=flag.project.organization,
          target=f"flag:{flag.id}", summary=flag.key)
    return flag


def toggle(flag: FeatureFlag, enabled: bool, *, user=None) -> FeatureFlag:
    flag.enabled = bool(enabled)
    flag.save(update_fields=["enabled", "updated_at"])
    audit("flag.toggle", actor=flag.created_by if user is None else user,
          organization=flag.project.organization, target=f"flag:{flag.id}",
          summary=f"{flag.key} -> {'on' if enabled else 'off'}")
    return flag


# --- evaluation (deterministic) ----------------------------------------------

def _bucket(key: str, subject: str) -> int:
    """Stable 0-99 bucket for a (flag, subject) pair, so a subject always gets the
    same answer for the same flag."""
    digest = hashlib.md5(f"{key}:{subject}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def evaluate(flag: FeatureFlag, context: dict | None = None) -> bool:
    """Is this flag on for the given context? Deterministic and honest."""
    if not flag.enabled or flag.archived:
        return False
    context = context or {}
    if flag.conditions and not match_conditions(flag.conditions, context):
        return False
    if flag.rollout >= 100:
        return True
    if flag.rollout <= 0:
        return False
    subject = str(context.get("subject") or context.get("user")
                  or context.get("id") or "")
    return _bucket(flag.key, subject) < flag.rollout


def is_enabled(project, key: str, context: dict | None = None) -> bool:
    flag = FeatureFlag.objects.filter(project=project, key=key, archived=False).first()
    return bool(flag and evaluate(flag, context))


def evaluate_all(project, context: dict | None = None) -> dict:
    return {f.key: evaluate(f, context)
            for f in project.feature_flags.filter(archived=False)}


def summary(project) -> dict:
    flags = list(project.feature_flags.filter(archived=False))
    return {
        "total": len(flags),
        "on": sum(1 for f in flags if f.enabled),
        "off": sum(1 for f in flags if not f.enabled),
        "targeted": sum(1 for f in flags if f.is_targeted),
    }
