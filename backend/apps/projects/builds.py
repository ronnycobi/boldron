"""Build orchestration service — the one place the build loop lives.

Both the web builder (apps/dashboard) and the mobile API (apps/projects/api)
call these, so "describe an app → create project → run the pipeline" behaves
identically on every interface. No build logic is duplicated in either UI.
"""
from __future__ import annotations

import re

from django.conf import settings

from apps.orchestrator.models import TERMINAL_STATUSES, AgentTask
from apps.orchestrator.service import Orchestrator
from apps.project_context.models import ContextEntry, ContextKind
from apps.project_context.services import ProjectContext
from apps.projects.models import Project

# Design artifacts that mark build progress (one context kind per phase).
PIPELINE = [
    ContextKind.REQUIREMENT,
    ContextKind.ARCHITECTURE,
    ContextKind.TECH_DECISION,
    ContextKind.API,
    ContextKind.SCHEMA,
    ContextKind.SCREEN,
    ContextKind.TESTING,
    ContextKind.REVIEW,
]
# The agents run, in order, for a build.
BUILD_PIPELINE = ["requirements", "architect", "database", "backend",
                  "frontend", "testing", "code_review", "security"]
NON_TERMINAL = [s for s, _ in AgentTask._meta.get_field("status").choices
                if s not in TERMINAL_STATUSES]

_NAME_ACRONYMS = {
    "crm": "CRM", "erp": "ERP", "hr": "HR", "api": "API", "saas": "SaaS",
    "ui": "UI", "ux": "UX", "ai": "AI", "pos": "POS", "cms": "CMS", "seo": "SEO",
    "b2b": "B2B", "b2c": "B2C", "mvp": "MVP",
    "ecommerce": "E-commerce", "e-commerce": "E-commerce",
}
_NAME_SMALL = {"a", "an", "the", "for", "and", "or", "of", "to", "with", "in", "on", "by"}


def default_stack() -> dict:
    """A sensible, runnable default stack so non-technical users never have to
    choose one. Backend + database are what the platform can generate AND run;
    frontend/mobile are design-led and left for the agents to shape."""
    return {"backend": "django", "database": "sqlite"}


def name_from_brief(brief: str) -> str:
    """Turn a plain-language brief into a clean, readable project title, e.g.
    'Build an online shopping website for my store with …' -> 'Online Shopping Website'."""
    text = re.sub(
        r"^\s*(?:please\s+)?(?:build|create|make|develop|design|generate|set\s+up)\s+"
        r"(?:me\s+)?(?:(?:a|an|the)\s+)?",
        "", brief.strip(), flags=re.I,
    )
    text = re.sub(r"\s+(?:with|that|which|where|including|featuring|so)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+for\s+(?:my|our|a|an|the)\b.*$", "", text, flags=re.I)
    text = (text.split(",")[0].splitlines() or [""])[0]

    words = text.strip(" .,-").split()[:6]
    if not words:
        return "New project"
    out = []
    for i, w in enumerate(words):
        lw = w.lower().strip(".,")
        if lw in _NAME_ACRONYMS:
            out.append(_NAME_ACRONYMS[lw])
        elif i and lw in _NAME_SMALL:
            out.append(lw)
        elif w.isupper():
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return (" ".join(out)[:60].strip(" -") or "New project")


def project_progress(project) -> int:
    """Rough build progress: share of the design pipeline that has content."""
    kinds = set(
        ContextEntry.objects.filter(project=project).values_list("kind", flat=True)
    )
    done = sum(1 for k in PIPELINE if k in kinds)
    return round(done / len(PIPELINE) * 100)


def project_state(project) -> str:
    from apps.deployments.models import DeploymentStatus

    if project.deployments.filter(status=DeploymentStatus.SUCCEEDED).exists():
        return "Deployed"
    if project.agent_tasks.filter(status__in=NON_TERMINAL).exists():
        return "Building"
    if project.mode == "import":
        return "Analyzing"
    return project.get_status_display()


def ran_on_stub(project) -> bool:
    """True if any build step ran on the offline stub (placeholder output)."""
    return project.agent_tasks.filter(model__istartswith="stub").exists()


def credit_summary(project) -> dict:
    """Live AI-credit snapshot: the org's current balance plus what this
    project's build has spent so far (real UsageRecord data)."""
    from decimal import Decimal

    from django.db.models import Sum

    from apps.credits.models import UsageRecord
    from apps.credits.services import get_account, plans

    acct = get_account(project.organization)
    used = UsageRecord.objects.filter(project=project).aggregate(
        credits=Sum("credits_charged"), cost=Sum("cost_usd"), tokens=Sum("total_tokens"))
    allowance = Decimal(str(plans().get(acct.plan, 0))) if acct else None
    balance = acct.balance if acct else None
    return {
        "has_account": acct is not None,
        "plan": acct.plan if acct else None,
        "balance": balance,
        "allowance": allowance,
        "remaining_pct": (int(min(balance, allowance) / allowance * 100)
                          if acct and allowance else None),
        "used_credits": used["credits"] or Decimal("0"),
        "used_cost": used["cost"] or Decimal("0"),
        "used_tokens": used["tokens"] or 0,
    }


def start_build(project, brief, user) -> None:
    """Queue and run the agent pipeline for a project from a brief. Runs the
    agents off the request thread (inline under tests for determinism)."""
    effective_brief = brief
    try:
        from apps.skills.service import apply_to_project, guidance_for
        _skills, guidance = guidance_for(brief, organization=project.organization, project=project)
        if guidance:
            effective_brief = f"{brief}\n\nApplied playbooks (guidance):\n{guidance}"
            apply_to_project(project, brief, user=user)
    except Exception:
        pass  # skills are additive guidance; never block a build

    orch = Orchestrator()
    previous = None
    for key in BUILD_PIPELINE:
        t = orch.create_task(project=project, agent_key=key,
                             input={"brief": effective_brief}, created_by=user)
        if previous is not None:
            t.depends_on.set([previous])
        previous = t

    def _execute():
        orch.run_ready(project)
        from apps.capabilities.infer import infer_capabilities
        if any(c.id == "ecommerce" for c in infer_capabilities(brief)):
            try:
                from apps.publishing.store_provision import provision_store
                provision_store(project, brief, user=user)
            except Exception:
                pass  # provisioning is best-effort; never break the build
        # Fire the real build.completed event to any subscribed org webhooks.
        try:
            from apps.developer.service import dispatch
            dispatch(project.organization, "build.completed", {
                "project_id": project.id,
                "project_name": project.name,
                "state": project_state(project),
                "progress": project_progress(project),
                "ran_on_stub": ran_on_stub(project),
            })
        except Exception:
            pass  # webhook delivery is best-effort; never break the build

    if getattr(settings, "RUNNING_TESTS", False):
        _execute()
    else:
        import threading

        from django.db import connection

        def _bg():
            try:
                _execute()
            finally:
                connection.close()  # don't leak this thread's DB connection

        threading.Thread(target=_bg, daemon=True).start()


def create_and_start_build(organization, brief, user) -> Project:
    """The full 'describe an app' flow: create the project (name + default
    stack), seed its workspace and requirement context, and start the build.
    Returns the new Project."""
    project = Project.objects.create(
        organization=organization,
        name=name_from_brief(brief),
        created_by=user,
        description=brief[:500],
        technology=default_stack(),
    )
    project.ensure_default_workspace()
    ProjectContext(project).set(
        ContextKind.REQUIREMENT, "brief", title="What to build",
        content=brief, source="builder",
    )
    start_build(project, brief, user)
    return project
