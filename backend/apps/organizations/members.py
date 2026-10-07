"""Membership management: change a member's role, remove a member, or leave.

Kept as a service so the safety rules live in one place:
- an organization must always keep at least one owner (never orphan a tenant);
- only an owner may grant/revoke ownership or remove another owner;
- managers (owner/admin) may manage members and admins;
- any member may leave (unless they are the only owner).
"""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.organizations.models import Membership, Role


class MemberError(Exception):
    pass


def _owner_count(organization) -> int:
    return Membership.objects.filter(organization=organization, role=Role.OWNER).count()


def _membership(organization, user) -> Membership | None:
    return Membership.objects.filter(organization=organization, user=user).first()


def change_member_role(organization, user, new_role, *, actor) -> Membership:
    if new_role not in Role.values:
        raise MemberError("Unknown role.")
    m = _membership(organization, user)
    if not m:
        raise MemberError("That person is not a member of this organization.")
    actor_m = _membership(organization, actor)
    if not actor_m or not actor_m.can_manage:
        raise MemberError("Owner or admin rights required.")
    # Only an owner may touch ownership (grant it or change an owner's role).
    if (m.role == Role.OWNER or new_role == Role.OWNER) and actor_m.role != Role.OWNER:
        raise MemberError("Only an owner can manage owner roles.")
    # Never demote the last remaining owner.
    if m.role == Role.OWNER and new_role != Role.OWNER and _owner_count(organization) <= 1:
        raise MemberError("Every organization needs at least one owner.")
    if m.role != new_role:
        m.role = new_role
        m.save(update_fields=["role"])
        audit("member.role_changed", actor=actor, organization=organization,
              target=f"user:{user.id}", summary=f"{user.email} → {new_role}")
    return m


def remove_member(organization, user, *, actor) -> None:
    m = _membership(organization, user)
    if not m:
        raise MemberError("That person is not a member of this organization.")
    actor_m = _membership(organization, actor)
    if not actor_m or not actor_m.can_manage:
        raise MemberError("Owner or admin rights required.")
    if m.role == Role.OWNER and actor_m.role != Role.OWNER:
        raise MemberError("Only an owner can remove an owner.")
    if m.role == Role.OWNER and _owner_count(organization) <= 1:
        raise MemberError("Every organization needs at least one owner.")
    m.delete()
    audit("member.removed", actor=actor, organization=organization,
          target=f"user:{user.id}", summary=f"removed {user.email}")


def leave_organization(organization, user) -> None:
    m = _membership(organization, user)
    if not m:
        raise MemberError("You're not a member of this organization.")
    if m.role == Role.OWNER and _owner_count(organization) <= 1:
        raise MemberError("Transfer ownership before leaving — you're the only owner.")
    m.delete()
    audit("member.left", actor=user, organization=organization,
          target=f"user:{user.id}", summary=f"{user.email} left")
