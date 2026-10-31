"""The automation engine (spec §10).

`fire(project, trigger, facts)` is what the platform calls when a real event
happens: it finds the project's ACTIVE automations for that trigger whose
conditions match the facts, runs their actions, and records a WorkflowRun with
each action's honest outcome.

Automations do not cascade: a re-entrancy guard means an action that itself
raises an event (e.g. opening an incident) never re-enters the engine, so there
are no loops and automations only fire from top-level platform events.
"""
from __future__ import annotations

import threading

from django.utils import timezone

from apps.automations import actions as action_registry
from apps.automations.models import RunStatus, Workflow, WorkflowRun
from apps.business_rules.engine import match_conditions

_depth = threading.local()


def _in_dispatch() -> bool:
    return getattr(_depth, "active", False)


def _summarize(results: list[dict]) -> str:
    if not results:
        return RunStatus.SKER
    outcomes = {r["outcome"] for r in results}
    if outcomes == {action_registry.DONE}:
        return RunStatus.COMPLETED
    if action_registry.DONE in outcomes:
        return RunStatus.PARTIAL
    if outcomes == {action_registry.SKIPPED}:
        return RunStatus.PARTIAL
    return RunStatus.FAILED


def run_workflow(workflow: Workflow, facts: dict, *, trigger=None, user=None) -> WorkflowRun:
    """Execute one workflow's actions against facts and record the run. Assumes the
    caller already decided the workflow should run (conditions matched)."""
    results = []
    for action in workflow.actions or []:
        if not isinstance(action, dict):
            continue
        outcome, detail = action_registry.run_action(
            action.get("type", ""), workflow.project, action.get("params", {}),
            facts, user)
        results.append({"action": action.get("type", ""),
                        "outcome": outcome, "detail": detail})
    run = WorkflowRun.objects.create(
        workflow=workflow, trigger=trigger or workflow.trigger,
        facts=facts or {}, status=_summarize(results), results=results)
    Workflow.objects.filter(pk=workflow.pk).update(
        run_count=workflow.run_count + 1, last_run_at=timezone.now())
    return run


def fire(project, trigger: str, facts: dict | None = None, *, user=None) -> list[WorkflowRun]:
    """Dispatch a real event to the project's matching active automations. Best-effort
    and loop-safe: never raises into the caller, and never re-enters itself."""
    if _in_dispatch():
        return []
    facts = facts or {}
    runs = []
    _depth.active = True
    try:
        workflows = Workflow.objects.filter(
            project=project, trigger=trigger, status="active")
        for wf in workflows:
            if match_conditions(wf.conditions or [], facts):
                runs.append(run_workflow(wf, facts, trigger=trigger, user=user))
    except Exception:
        # Automations must never break the platform event that fired them.
        pass
    finally:
        _depth.active = False
    return runs


def run_now(workflow: Workflow, facts: dict | None = None, *, user=None) -> WorkflowRun:
    """Manually run one workflow (the builder's 'test' / run action). Conditions are
    still honoured so the test reflects real behaviour; records trigger='manual'."""
    facts = facts or {}
    if not match_conditions(workflow.conditions or [], facts):
        return WorkflowRun.objects.create(
            workflow=workflow, trigger="manual", facts=facts,
            status=RunStatus.SKER,
            results=[{"action": "", "outcome": "skipped",
                      "detail": "Conditions did not match these facts."}])
    return run_workflow(workflow, facts, trigger="manual", user=user)


def fire_safe(project, trigger: str, facts: dict | None = None, *, user=None):
    """Convenience for emitters: fire() already swallows errors, but guard the
    import/call site too so a wiring point can never break its host flow."""
    try:
        return fire(project, trigger, facts, user=user)
    except Exception:
        return []
