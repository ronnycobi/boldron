"""Automation lifecycle (spec §10-11): create / update / activate / pause, with
validation so only real triggers and actions can be saved."""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.automations import actions as action_registry
from apps.automations import triggers as trigger_registry
from apps.automations.models import Workflow, WorkflowStatus
from apps.business_rules.engine import OPERATORS


class AutomationError(Exception):
    pass


def _validate_conditions(conditions):
    if not isinstance(conditions, list):
        raise AutomationError("Conditions must be a list.")
    for i, c in enumerate(conditions):
        if not isinstance(c, dict) or not str(c.get("fact", "")).strip():
            raise AutomationError(f"Condition {i} needs a fact.")
        if c.get("op") not in OPERATORS:
            raise AutomationError(f"Condition {i} has an unknown operator.")
        if "value" not in c:
            raise AutomationError(f"Condition {i} needs a value.")


def _validate_actions(actions):
    if not isinstance(actions, list) or not actions:
        raise AutomationError("An automation needs at least one action.")
    for i, a in enumerate(actions):
        if not isinstance(a, dict) or not action_registry.is_valid(a.get("type", "")):
            raise AutomationError(f"Action {i} has an unknown type.")


def create(project, *, name, trigger, actions, description="", conditions=None,
           user=None) -> Workflow:
    name = (name or "").strip()
    if not name:
        raise AutomationError("An automation needs a name.")
    if not trigger_registry.is_valid(trigger):
        raise AutomationError(f"Unknown trigger '{trigger}'.")
    conditions = conditions or []
    _validate_conditions(conditions)
    _validate_actions(actions)
    wf = Workflow.objects.create(
        project=project, name=name[:200], description=(description or "").strip(),
        trigger=trigger, conditions=conditions, actions=actions,
        created_by=user)
    audit("automation.create", actor=user, organization=project.organization,
          target=f"automation:{wf.id}", summary=f"{name} on {trigger}")
    return wf


def update(wf: Workflow, *, user=None, **fields) -> Workflow:
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise AutomationError("An automation needs a name.")
        wf.name = name[:200]
    if "description" in fields:
        wf.description = (fields["description"] or "").strip()
    if "trigger" in fields:
        if not trigger_registry.is_valid(fields["trigger"]):
            raise AutomationError(f"Unknown trigger '{fields['trigger']}'.")
        wf.trigger = fields["trigger"]
    if "conditions" in fields:
        _validate_conditions(fields["conditions"] or [])
        wf.conditions = fields["conditions"] or []
    if "actions" in fields:
        _validate_actions(fields["actions"])
        wf.actions = fields["actions"]
    wf.save()
    audit("automation.update", actor=user, organization=wf.project.organization,
          target=f"automation:{wf.id}", summary=wf.name[:120])
    return wf


def set_status(wf: Workflow, status: str, *, user=None) -> Workflow:
    if status not in WorkflowStatus.values:
        raise AutomationError(f"Unknown status '{status}'.")
    wf.status = status
    wf.save(update_fields=["status", "updated_at"])
    audit("automation.status", actor=user, organization=wf.project.organization,
          target=f"automation:{wf.id}", summary=f"{wf.name} → {status}")
    return wf


def summary(project) -> dict:
    wfs = list(project.automations.all())
    return {
        "total": len(wfs),
        "active": sum(1 for w in wfs if w.status == WorkflowStatus.ACTIVE),
        "draft": sum(1 for w in wfs if w.status == WorkflowStatus.DRAFT),
        "paused": sum(1 for w in wfs if w.status == WorkflowStatus.PAUSED),
        "runs": sum(w.run_count for w in wfs),
    }
