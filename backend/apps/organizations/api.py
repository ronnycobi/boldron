"""Organizations & teams API (mobile/API client).

Thin HTTP layer over the existing tenant services — access.py for scoping,
members.py and invitations.py for the safety rules (last-owner protection,
role checks, invite acceptance). No business logic is duplicated here.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.credits.services import ensure_account
from apps.organizations import invitations as invites
from apps.organizations import members as members_svc
from apps.organizations.access import organizations_for
from apps.organizations.models import Invitation, Organization, Role
from apps.organizations.serializers import (
    InvitationSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)


def _get_org(user, pk) -> Organization:
    """The organization with this id that the user belongs to, else 404."""
    return get_object_or_404(organizations_for(user), pk=pk)


def _require_manage(org, user) -> Response | None:
    m = org.memberships.filter(user=user).first()
    if not (m and m.role in {Role.OWNER, Role.ADMIN}):
        return Response(
            {"detail": "Owner or admin rights required."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class OrganizationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orgs = organizations_for(request.user).order_by("name")
        return Response(
            OrganizationSerializer(orgs, many=True, context={"request": request}).data
        )

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"name": ["An organization name is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org = Organization.objects.create(name=name, created_by=request.user)
        org.add_member(request.user, role=Role.OWNER)
        ensure_account(org, plan="free")
        return Response(
            OrganizationSerializer(org, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        org = _get_org(request.user, pk)
        return Response(OrganizationSerializer(org, context={"request": request}).data)

    def patch(self, request, pk):
        from apps.organizations.permissions import has_perm

        org = _get_org(request.user, pk)
        if not has_perm(request.user, org, "org.manage"):
            return Response(
                {"detail": "You don't have permission to edit this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )
        updates = []
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                return Response(
                    {"name": ["An organization name is required."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            org.name = name
            updates.append("name")
        if "description" in request.data:
            org.description = (request.data.get("description") or "").strip()[:2000]
            updates.append("description")
        if updates:
            org.save(update_fields=updates + ["updated_at"])
            from apps.settings.service import audit_change
            audit_change("organization.updated", actor=request.user,
                         organization=org, summary=f"updated {', '.join(updates)}")
        return Response(OrganizationSerializer(org, context={"request": request}).data)


class OrganizationRolesView(APIView):
    """The organization's role → permission matrix (an honest reference of what
    each built-in role can do) plus the caller's own permissions."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.organizations.permissions import (
            PERMISSIONS,
            permissions_for_member,
            role_matrix,
        )

        org = _get_org(request.user, pk)
        return Response({
            "roles": [
                {"key": r.value, "label": r.label} for r in Role
            ],
            "permissions": PERMISSIONS,
            "matrix": role_matrix(),
            "my_permissions": permissions_for_member(request.user, org),
        })


class OrganizationAiView(APIView):
    """The organization's AI routing preferences + the real options available.

    Read is open to any member; changing requires org management rights. No API
    keys are ever read or written here — only which providers are connected and
    which the org prefers."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.ai_providers.registry import generation_status
        from apps.organizations import ai_settings
        from apps.organizations.permissions import has_perm

        org = _get_org(request.user, pk)
        return Response({
            "preferences": ai_settings.preferences_for(org),
            "options": ai_settings.available_options(),
            "generation": generation_status(),
            "can_manage": has_perm(request.user, org, "org.manage"),
        })

    def patch(self, request, pk):
        from apps.organizations import ai_settings
        from apps.organizations.permissions import has_perm

        org = _get_org(request.user, pk)
        if not has_perm(request.user, org, "org.manage"):
            return Response(
                {"detail": "You don't have permission to change AI settings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            ai_settings.set_preferences(
                org,
                preferred_provider=request.data.get("preferred_provider", "") or "",
                preferred_model=request.data.get("preferred_model", "") or "",
                actor=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"preferences": ai_settings.preferences_for(org)})


class MemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        org = _get_org(request.user, pk)
        members = org.memberships.select_related("user").order_by("role", "user__email")
        return Response(MembershipSerializer(members, many=True).data)


class MemberDetailView(APIView):
    """Change a member's role (PATCH) or remove them (DELETE). Guarded by the
    members service, which enforces last-owner protection and role authority."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, user_id):
        org = _get_org(request.user, pk)
        target = get_object_or_404(User, pk=user_id)
        try:
            members_svc.change_member_role(
                org, target, request.data.get("role") or Role.MEMBER, actor=request.user
            )
        except members_svc.MemberError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        m = org.memberships.select_related("user").get(user=target)
        return Response(MembershipSerializer(m).data)

    def delete(self, request, pk, user_id):
        org = _get_org(request.user, pk)
        target = get_object_or_404(User, pk=user_id)
        try:
            members_svc.remove_member(org, target, actor=request.user)
        except members_svc.MemberError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeaveOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        org = _get_org(request.user, pk)
        try:
            members_svc.leave_organization(org, request.user)
        except members_svc.MemberError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _send_invite(request, inv) -> None:
    from django.urls import reverse

    from apps.notifications.email import send_invitation_email

    link = request.build_absolute_uri(reverse("dashboard:accept_invite", args=[inv.token]))
    try:
        send_invitation_email(inv, link)
    except Exception:
        pass  # delivery is best-effort; the invite still stands


class InvitationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        invs = org.invitations.all()
        return Response(InvitationSerializer(invs, many=True).data)

    def post(self, request, pk):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        try:
            inv = invites.create_invitation(
                org,
                request.data.get("email", ""),
                role=request.data.get("role") or Role.MEMBER,
                invited_by=request.user,
            )
        except invites.InvitationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _send_invite(request, inv)
        return Response(InvitationSerializer(inv).data, status=status.HTTP_201_CREATED)


class InvitationRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, inv_id):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        inv = get_object_or_404(Invitation, pk=inv_id, organization=org)
        invites.revoke_invitation(inv)
        return Response(InvitationSerializer(inv).data)


class InvitationResendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, inv_id):
        org = _get_org(request.user, pk)
        denied = _require_manage(org, request.user)
        if denied:
            return denied
        inv = get_object_or_404(Invitation, pk=inv_id, organization=org)
        try:
            invites.resend_invitation(inv)
        except invites.InvitationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _send_invite(request, inv)
        return Response(InvitationSerializer(inv).data)


class AcceptInvitationView(APIView):
    """Accept an invitation by its token. The accepting user's email must match
    the invited address (enforced by the service)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        try:
            membership = invites.accept_invitation(token, request.user)
        except invites.InvitationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            OrganizationSerializer(membership.organization, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
