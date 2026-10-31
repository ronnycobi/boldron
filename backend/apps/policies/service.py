"""Policy lifecycle (spec §44): create / update / enable, with validation so a
policy can only target a scope the platform actually enforces."""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.business_rules.engine import OPERATORS
from apps.policies.models import Policy, PolicyEffect, PolicyScope

# Scopes the platform genuinely consults — a policy can't be created for anything
# else, so no policy is governance-in-name-only.
ENFORCED_SCOPES = {PolicyScope.DEPLOY}


class PolicyError(Exception):
    pass


def _validate_conditions(conditions):
    if not isinstance(conditions, list):
        raise PolicyError("Conditions must be a list.")
    for i, c in enumerate(conditions):
        if not isinstance(c, dict) or not str(c.get("fact", "")).strip():
            raise PolicyError(f"Condition {i} needs a fact.")
        if c.get("op") not in OPERATORS:
            raise PolicyError(f"Condition {i} has an unknown operator.")
        if "value" not in c:
            raise PolicyError(f"Condition {i} needs a value.")


def create(project, *, name, scope="deploy", effect="block", description="",
           conditions=None, message="", user=None) -> Policy:
    name = (name or "").strip()
    if not name:
        raise PolicyError("A policy needs a name.")
    if scope not in ENFORCED_SCOPES:
        raise PolicyError(f"'{scope}' is not an enforced scope yet.")
    if effect not in PolicyEffect.values:
        raise PolicyError(f"Unknown effect '{effect}'.")
    conditions = conditions or []
    _validate_conditions(conditions)
    policy = Policy.objects.create(
        project=project, name=name[:200], scope=scope, effect=effect,
        description=(description or "").strip(), conditions=conditions,
        message=(message or "").strip()[:300], created_by=user)
    audit("policy.create", actor=user, organization=project.organization,
          target=f"policy:{policy.id}", summary=f"{name} ({effect} on {scope})")
    return policy


def update(policy: Policy, *, user=None, **fields) -> Policy:
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise PolicyError("A policy needs a name.")
        policy.name = name[:200]
    if "description" in fields:
        policy.description = (fields["description"] or "").strip()
    if "effect" in fields:
        if fields["effect"] not in PolicyEffect.values:
            raise PolicyError(f"Unknown effect '{fields['effect']}'.")
        policy.effect = fields["effect"]
    if "conditions" in fields:
        _validate_conditions(fields["conditions"] or [])
        policy.conditions = fields["conditions"] or []
    if "message" in fields:
        policy.message = (fields["message"] or "").strip()[:300]
    if "enabled" in fields:
        policy.enabled = bool(fields["enabled"])
    policy.save()
    audit("policy.update", actor=user, organization=policy.project.organization,
          target=f"policy:{policy.id}", summary=policy.name[:120])
    return policy


def set_enabled(policy: Policy, enabled: bool, *, user=None) -> Policy:
    policy.enabled = bool(enabled)
    policy.save(update_fields=["enabled", "updated_at"])
    audit("policy.toggle", actor=user, organization=policy.project.organization,
          target=f"policy:{policy.id}",
          summary=f"{policy.name} {'enabled' if enabled else 'disabled'}")
    return policy


def built_in_guardrails(project) -> list[dict]:
    """The platform's own always-on guardrails, surfaced read-only so the
    governance picture is complete and honest. These describe REAL gates already
    enforced elsewhere (deployments pre-flight, the security ledger)."""
    return [
        {"name": "Production approval required", "effect": "require_approval",
         "detail": "Every production deploy must be approved by an owner or admin "
                   "before it runs.", "built_in": True},
        {"name": "No high-severity security findings", "effect": "block",
         "detail": "A production deploy is blocked while the latest security scan "
                   "has an unresolved high-severity finding.", "built_in": True},
        {"name": "Pre-deploy guardrails", "effect": "block",
         "detail": "Configured pre-deploy hooks (tests, security, sign-off) can "
                   "block a deploy before anything ships.", "built_in": True},
    ]


def summary(project) -> dict:
    policies = list(project.policies.all())
    return {
        "total": len(policies),
        "enabled": sum(1 for p in policies if p.enabled),
        "blocking": sum(1 for p in policies if p.enabled and p.effect == "block"),
        "built_in": len(built_in_guardrails(project)),
    }
