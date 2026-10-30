"""Acceptance-criteria lifecycle (spec §3).

Promote the criteria the Requirements Agent embedded in each requirement into
trackable records, let a person verify them, and report an HONEST acceptance
status for the project — never claiming "accepted" without evidence.
"""
from __future__ import annotations

from django.utils import timezone

from apps.acceptance.models import AcceptanceCriterion, CriterionStatus, VERIFIED_STATUSES
from apps.audit.service import record as audit
from apps.project_context.models import ContextKind


class AcceptanceError(Exception):
    pass


def add(project, statement, *, requirement=None, source="user", user=None) -> AcceptanceCriterion:
    statement = (statement or "").strip()
    if not statement:
        raise AcceptanceError("A criterion needs a statement.")
    # Append after any existing criteria for the same requirement.
    last = (AcceptanceCriterion.objects
            .filter(project=project, requirement=requirement)
            .order_by("-order").first())
    crit = AcceptanceCriterion.objects.create(
        project=project, requirement=requirement, statement=statement[:2000],
        source=source, order=(last.order + 1) if last else 0)
    audit("acceptance.add", actor=user, organization=project.organization,
          target=f"criterion:{crit.id}", summary=statement[:120])
    return crit


def import_from_requirements(project, *, user=None) -> int:
    """Promote the `acceptance_criteria` strings embedded in REQUIREMENT context
    entries into first-class records. Idempotent: a criterion already imported for
    a requirement (same statement) is skipped, so re-running never duplicates."""
    created = 0
    reqs = project.context_entries.filter(kind=ContextKind.REQUIREMENT)
    for req in reqs:
        criteria = (req.data or {}).get("acceptance_criteria") or []
        if not isinstance(criteria, list):
            continue
        for i, raw in enumerate(criteria):
            stmt = str(raw).strip()
            if not stmt:
                continue
            if AcceptanceCriterion.objects.filter(
                    project=project, requirement=req, statement=stmt[:2000]).exists():
                continue
            AcceptanceCriterion.objects.create(
                project=project, requirement=req, statement=stmt[:2000],
                order=i, source=f"requirement:{req.key}")
            created += 1
    if created:
        audit("acceptance.import", actor=user, organization=project.organization,
              target=f"project:{project.id}", summary=f"Imported {created} criteria")
    return created


def verify(criterion: AcceptanceCriterion, status: str, *, user=None, note="") -> AcceptanceCriterion:
    """Set a criterion's status. met / not-met / waived stamp who decided and when;
    moving back to pending clears that provenance so the record stays honest."""
    if status not in CriterionStatus.values:
        raise AcceptanceError(f"Unknown status '{status}'.")
    criterion.status = status
    if status in VERIFIED_STATUSES:
        criterion.verified_by = user
        criterion.verified_at = timezone.now()
    else:
        criterion.verified_by = None
        criterion.verified_at = None
    if note:
        criterion.note = note[:2000]
    criterion.save()
    audit("acceptance.verify", actor=user,
          organization=criterion.project.organization,
          target=f"criterion:{criterion.id}", summary=f"→ {status}")
    return criterion


def summary(project) -> dict:
    """The project's acceptance status. `accepted` is True only when there is at
    least one criterion, none is pending or not-met, and at least one is actually
    met (all-waived is never reported as accepted)."""
    crits = list(project.acceptance_criteria.all())
    counts = {s: 0 for s in CriterionStatus.values}
    for c in crits:
        counts[c.status] = counts.get(c.status, 0) + 1
    total = len(crits)
    met = counts[CriterionStatus.MET]
    pending = counts[CriterionStatus.PENDING]
    failed = counts[CriterionStatus.FAILED]
    waived = counts[CriterionStatus.WAIVED]
    accepted = bool(total) and pending == 0 and failed == 0 and met >= 1
    return {
        "total": total,
        "met": met,
        "pending": pending,
        "failed": failed,
        "waived": waived,
        "checked": total - pending,
        "met_pct": round(met / total * 100) if total else None,
        "accepted": accepted,
    }


def acceptance_met(project) -> bool:
    """Reusable gate: are this project's acceptance criteria genuinely met?"""
    return summary(project)["accepted"]
