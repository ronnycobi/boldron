"""Account-lifecycle service (spec §42-43): status changes with a recorded reason,
honest enforcement, and appeals."""
from __future__ import annotations

from django.utils import timezone

from apps.audit.service import record as audit
from apps.governance.models import (
    BLOCKED_STATUSES,
    AccountAction,
    AccountState,
    AccountStatus,
    Appeal,
)


class GovernanceError(Exception):
    pass


def current_status(organization) -> str:
    state = AccountState.objects.filter(organization=organization).first()
    return state.status if state else AccountStatus.ACTIVE


def is_blocked(organization) -> bool:
    """Suspended/terminated accounts cannot use the service; restricted can."""
    return current_status(organization) in BLOCKED_STATUSES


def require_active(organization):
    """Guard used at real action points. Raises GovernanceError when the account
    is suspended/terminated, with a clear, honest message."""
    status = current_status(organization)
    if status in BLOCKED_STATUSES:
        raise GovernanceError(
            f"This account is {status}. Please contact support or submit an appeal.")


def set_status(organization, status, *, reason="", policy_section="", evidence="",
               actor=None) -> AccountAction:
    if status not in AccountStatus.values:
        raise GovernanceError(f"Unknown status '{status}'.")
    if status in BLOCKED_STATUSES and not reason:
        raise GovernanceError("Suspending or terminating an account requires a reason.")
    previous = current_status(organization)
    state, _ = AccountState.objects.get_or_create(organization=organization)
    state.status = status
    state.save(update_fields=["status", "updated_at"])
    action = AccountAction.objects.create(
        organization=organization, from_status=previous, to_status=status,
        reason=reason, policy_section=policy_section[:120], evidence=evidence, actor=actor)
    audit("account.status", actor=actor, organization=organization,
          target=f"org:{organization.id}", summary=f"{previous} -> {status}")
    return action


def submit_appeal(organization, user, *, reason, evidence="", action=None) -> Appeal:
    reason = (reason or "").strip()
    if not reason:
        raise GovernanceError("An appeal needs a reason.")
    appeal = Appeal.objects.create(
        organization=organization, action=action, reason=reason, evidence=evidence,
        submitted_by=user)
    audit("account.appeal", actor=user, organization=organization,
          target=f"org:{organization.id}", summary="appeal submitted")
    return appeal


def decide_appeal(appeal: Appeal, outcome, *, resolution="", reviewer=None,
                  restore_status=None) -> Appeal:
    if outcome not in Appeal.Outcome.values:
        raise GovernanceError(f"Unknown outcome '{outcome}'.")
    appeal.outcome = outcome
    appeal.status = Appeal.Status.DECIDED
    appeal.resolution = resolution
    appeal.reviewed_by = reviewer
    appeal.decided_at = timezone.now()
    appeal.save()
    # A reversal can restore the account to active (or a named status).
    if outcome == Appeal.Outcome.REVERSED:
        set_status(appeal.organization, restore_status or AccountStatus.ACTIVE,
                   reason=f"Appeal {appeal.id} upheld", actor=reviewer)
    audit("account.appeal_decided", actor=reviewer, organization=appeal.organization,
          target=f"appeal:{appeal.id}", summary=outcome)
    return appeal


def history(organization):
    return AccountAction.objects.filter(organization=organization)


def summary() -> dict:
    states = AccountState.objects.all()
    return {
        "suspended": states.filter(status=AccountStatus.SUSPENDED).count(),
        "terminated": states.filter(status=AccountStatus.TERMINATED).count(),
        "restricted": states.filter(status=AccountStatus.RESTRICTED).count(),
        "open_appeals": Appeal.objects.exclude(status=Appeal.Status.DECIDED).count(),
    }
