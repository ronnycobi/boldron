"""Shared new-user onboarding.

Both the web sign-up view and the mobile registration API call this, so the
sequence — first organization, owner membership, free-tier credit account,
address-verification email — lives in exactly one place and can never drift
between the two interfaces.
"""
from __future__ import annotations

from apps.accounts import verification
from apps.credits.services import ensure_account
from apps.organizations.models import Organization, Role


def onboard_user(user, *, org_name: str = "", request=None) -> Organization:
    """Provision a freshly created user: create their first organization (they
    are its owner), start a free-tier credit account, and — when a request is
    given (needed to build the absolute link) — send the verification email.

    Returns the created Organization.
    """
    default_name = f"{user.full_name or user.email.split('@')[0]}'s workspace"
    org = Organization.objects.create(
        name=(org_name or "").strip() or default_name, created_by=user
    )
    org.add_member(user, role=Role.OWNER)
    ensure_account(org, plan="free")  # free-tier credits
    if request is not None:
        verification.send_verification(request, user)  # best-effort; never raises
    return org
