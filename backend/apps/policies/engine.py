"""Policy decision engine (spec §44) — deterministic, consulted at the action's
real decision point."""
from __future__ import annotations

from apps.business_rules.engine import match_conditions


def decide(project, scope: str, context: dict | None = None) -> dict:
    """Evaluate the project's enabled policies for a scope against the action's
    context. Returns the decision: what blocks it, what requires approval, and any
    warnings. `allowed` is False as soon as any block policy matches."""
    context = context or {}
    blocks, approvals, warnings = [], [], []
    for p in project.policies.filter(scope=scope, enabled=True):
        if not match_conditions(p.conditions or [], context):
            continue
        item = {"policy": p.name, "message": p.reason}
        if p.effect == "block":
            blocks.append(item)
        elif p.effect == "require_approval":
            approvals.append(item)
        else:
            warnings.append(item)
    return {
        "allowed": not blocks,
        "blocks": blocks,
        "require_approval": approvals,
        "warnings": warnings,
    }
