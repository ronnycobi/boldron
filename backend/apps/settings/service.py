"""Settings control-center aggregation.

This is the foundation of the Settings subsystem: it does NOT own data — it
reads the owning domain apps (accounts, organizations, credits, publishing, …)
and presents a single, scoped, status-aware overview that both the web pages and
the mobile API consume.

Three scopes are kept strictly separate — user, organization, project — so a
personal preference never becomes an org setting, and one org/project never
affects another. Every section declares whether it is `available` yet, so the
control center shows the full map honestly (built sections link; the rest are
clearly "coming", never fake).
"""
from __future__ import annotations

from decimal import Decimal


# --- the settings map (the full control-center structure) -------------------
# `available=True` means the section is wired to a real page/endpoint today.
# Phases fill in the rest; nothing here fabricates a setting.

def _account_sections() -> list[dict]:
    return [
        {"key": "profile", "label": "Profile", "available": True, "route": "dashboard:account"},
        {"key": "security", "label": "Security", "available": True, "route": "dashboard:security_center"},
        {"key": "sessions", "label": "Sessions", "available": True, "route": "dashboard:security_center"},
        {"key": "appearance", "label": "Appearance", "available": True, "route": "dashboard:settings"},
        {"key": "accessibility", "label": "Accessibility", "available": True, "route": "dashboard:settings"},
        {"key": "notifications", "label": "Notifications", "available": False},
        {"key": "connected", "label": "Connected accounts", "available": False},
    ]


def _org_sections() -> list[dict]:
    return [
        {"key": "general", "label": "General", "available": True, "route": "dashboard:org_settings"},
        {"key": "members", "label": "Members", "available": True, "route": "dashboard:people"},
        {"key": "roles", "label": "Roles & permissions", "available": True, "route": "dashboard:org_roles"},
        {"key": "billing", "label": "Billing & plan", "available": True, "route": "dashboard:settings"},
        {"key": "usage", "label": "Usage", "available": True, "route": "dashboard:usage"},
        {"key": "ai", "label": "AI", "available": True, "route": "dashboard:org_ai"},
        {"key": "integrations", "label": "Integrations", "available": True, "route": "dashboard:org_integrations"},
        {"key": "developer", "label": "Developer & API", "available": True, "route": "dashboard:org_developer"},
        {"key": "domains", "label": "Domains", "available": False},
        {"key": "documents", "label": "Documents", "available": False},
        {"key": "commerce", "label": "Commerce", "available": False},
        {"key": "notifications", "label": "Notifications", "available": False},
        {"key": "privacy", "label": "Privacy", "available": False},
        {"key": "data", "label": "Data", "available": False},
        {"key": "audit", "label": "Audit log", "available": False},
    ]


def _project_sections() -> list[dict]:
    # Project settings are per-project; the control center links to the project
    # workspace, where build/deploy/website/etc. already live.
    return [
        {"key": "general", "label": "General", "available": True, "scope_note": "per project"},
        {"key": "build", "label": "Build", "available": True, "scope_note": "per project"},
        {"key": "deployment", "label": "Deployment", "available": True, "scope_note": "per project"},
        {"key": "domains", "label": "Domains", "available": True, "scope_note": "per project"},
        {"key": "ai", "label": "AI", "available": False},
        {"key": "environment", "label": "Environment & secrets", "available": True, "scope_note": "per project"},
        {"key": "repository", "label": "Repository", "available": False},
        {"key": "analytics", "label": "Analytics", "available": True, "scope_note": "per project"},
        {"key": "security", "label": "Security", "available": True, "scope_note": "per project"},
    ]


def sections_catalog() -> dict:
    return {
        "account": _account_sections(),
        "organization": _org_sections(),
        "project": _project_sections(),
    }


# --- live status + alerts (REAL data only) ----------------------------------

def alerts_for(user) -> list[dict]:
    """Actionable alerts derived strictly from real state. Returns an empty list
    when all is well — never a fabricated warning."""
    from apps.credits.services import get_account, plans
    from apps.organizations.access import organizations_for
    from apps.publishing.models import CustomDomain

    orgs = list(organizations_for(user))
    alerts: list[dict] = []

    if not user.email_verified:
        alerts.append({
            "level": "warning", "area": "account",
            "title": "Email not verified",
            "detail": "Verify your email to unlock building and deployment.",
            "route": "dashboard:account",
        })

    plan_allowance = plans()
    for org in orgs:
        acct = get_account(org)
        if acct is None:
            continue
        allowance = Decimal(str(plan_allowance.get(acct.plan, 0)))
        if allowance and (acct.balance / allowance) < Decimal("0.15"):
            alerts.append({
                "level": "warning", "area": "billing",
                "title": "AI credits are low",
                "detail": f"{org.name}: {int(acct.balance)} credits left of {int(allowance)}.",
                "route": "dashboard:settings",
            })

    unverified = (
        CustomDomain.objects.filter(website__project__organization__in=orgs)
        .exclude(verification_status=CustomDomain.VERIFY_VERIFIED)
        .count()
    )
    if unverified:
        alerts.append({
            "level": "warning", "area": "domains",
            "title": "Domain needs verification",
            "detail": f"{unverified} custom domain(s) are awaiting DNS verification.",
            "route": None,
        })

    return alerts


def account_status(user) -> dict:
    """Per-section status for the account scope (real data)."""
    return {
        "email": user.email,
        "email_verified": user.email_verified,
        "display_name": user.display_name,
        # MFA is not implemented yet (Phase 1). Report it honestly as unavailable
        # rather than inventing an 'enabled/disabled' state.
        "mfa_available": False,
    }


def organization_status(user) -> list[dict]:
    from apps.credits.services import get_account, plans
    from apps.organizations.access import manageable_organizations_for, organizations_for

    manage_ids = set(manageable_organizations_for(user).values_list("id", flat=True))
    plan_allowance = plans()
    out = []
    for org in organizations_for(user).order_by("name"):
        membership = org.memberships.filter(user=user).first()
        acct = get_account(org)
        allowance = Decimal(str(plan_allowance.get(acct.plan, 0))) if acct else Decimal("0")
        pct = int(min(acct.balance, allowance) / allowance * 100) if acct and allowance else None
        out.append({
            "id": org.id,
            "name": org.name,
            "role": membership.role if membership else None,
            "can_manage": org.id in manage_ids,
            "plan": acct.plan if acct else None,
            "credits_pct": pct,
            "members": org.memberships.count(),
        })
    return out


def overview(user) -> dict:
    """The full control-center payload: alerts + account/org status + the map."""
    return {
        "alerts": alerts_for(user),
        "account": account_status(user),
        "organizations": organization_status(user),
        "sections": sections_catalog(),
    }


# --- permissions -------------------------------------------------------------

def can_view_org_settings(user, org) -> bool:
    """Any member may view org settings; mutations are gated separately."""
    return org.memberships.filter(user=user).exists()


def can_manage_org_settings(user, org) -> bool:
    from apps.organizations.models import Role

    m = org.memberships.filter(user=user).first()
    return bool(m and m.role in {Role.OWNER, Role.ADMIN})


# --- audit -------------------------------------------------------------------

def audit_change(action: str, *, actor, organization=None, summary: str = "", **metadata) -> None:
    """Record a settings change in the platform audit log. Use for every
    mutating settings action so changes are always attributable."""
    from apps.audit.service import record

    record(
        f"settings.{action}",
        actor=actor,
        organization=organization,
        summary=summary,
        metadata=metadata or None,
    )
