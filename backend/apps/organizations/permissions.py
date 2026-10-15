"""Organization RBAC — the single source of truth for what each role can do.

The platform has three built-in roles (owner / admin / member). Historically the
authorization checks were scattered as ``role in {OWNER, ADMIN}`` tests; this
module names the actual capabilities and maps each role to the permissions it
really holds, so the Roles & Permissions screen can show an honest matrix and new
code can gate on a named permission instead of a hard-coded role set.

This describes the capabilities that genuinely exist and are enforced today — it
is not a promise of finer-grained control than the app actually has. Custom roles
are intentionally not offered yet: there is no second privilege tier to grant, so
a role builder would be a control that changes nothing.
"""
from __future__ import annotations

from apps.organizations.models import Role

# Capability catalog. Each key gates a real, enforced action somewhere in the app.
PERMISSIONS = [
    {"key": "org.manage", "label": "Edit organization settings",
     "description": "Change the organization's name and details."},
    {"key": "members.manage", "label": "Manage members",
     "description": "Invite and remove members and change their roles."},
    {"key": "ownership.manage", "label": "Manage owners",
     "description": "Grant or revoke ownership and remove owners."},
    {"key": "billing.manage", "label": "Manage billing & plan",
     "description": "View billing and request plan changes."},
    {"key": "projects.manage", "label": "Manage projects",
     "description": "Rename and delete the organization's projects."},
]

PERMISSION_KEYS = [p["key"] for p in PERMISSIONS]

# Role → permissions. Owner is a superset of admin plus the ownership-only
# capabilities; members hold none of the management permissions (read/use only).
_ADMIN = {"org.manage", "members.manage", "billing.manage", "projects.manage"}
ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.OWNER: _ADMIN | {"ownership.manage"},
    Role.ADMIN: set(_ADMIN),
    Role.MEMBER: set(),
}


def permissions_for_role(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def has_perm(user, organization, key: str) -> bool:
    """True if the user's role in this organization grants the permission."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    m = organization.memberships.filter(user=user).first()
    if not m:
        return False
    return key in ROLE_PERMISSIONS.get(m.role, set())


def permissions_for_member(user, organization) -> list[str]:
    """The permission keys the user holds in this organization (sorted)."""
    m = organization.memberships.filter(user=user).first()
    if not m:
        return []
    return sorted(ROLE_PERMISSIONS.get(m.role, set()))


def role_matrix() -> list[dict]:
    """Display matrix: one row per permission with a bool per built-in role."""
    rows = []
    for perm in PERMISSIONS:
        rows.append({
            "key": perm["key"],
            "label": perm["label"],
            "description": perm["description"],
            "roles": {
                role: perm["key"] in perms
                for role, perms in ROLE_PERMISSIONS.items()
            },
        })
    return rows
