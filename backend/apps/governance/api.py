"""Account-governance API (spec §42-43).

Customer: see their org's account status + history, and submit an appeal.
Staff: change status (with a reason) and decide appeals. Governance records are
sensitive — a customer only sees their own org's.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.governance import service
from apps.governance.models import AccountAction, Appeal
from apps.organizations.access import manageable_organizations_for, organizations_for


class AccountStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, org_pk):
        org = get_object_or_404(organizations_for(request.user), pk=org_pk)
        return Response({
            "status": service.current_status(org),
            "history": [{"from": a.from_status, "to": a.to_status, "reason": a.reason,
                         "at": a.created_at.isoformat()}
                        for a in service.history(org)[:50]],
        })


class AppealView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, org_pk):
        # Only an owner/admin of the org can appeal on its behalf.
        org = get_object_or_404(manageable_organizations_for(request.user), pk=org_pk)
        try:
            appeal = service.submit_appeal(
                org, request.user, reason=request.data.get("reason", ""),
                evidence=request.data.get("evidence", ""))
        except service.GovernanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"id": appeal.id, "status": appeal.status}, status=201)


class _StaffView(APIView):
    permission_classes = [IsAuthenticated]

    def _staff(self, request):
        if not request.user.is_staff:
            raise PermissionDenied("Staff only.")


class StaffAccountView(_StaffView):
    def post(self, request, org_pk):
        self._staff(request)
        from apps.organizations.models import Organization
        org = get_object_or_404(Organization, pk=org_pk)
        try:
            action = service.set_status(
                org, request.data.get("status", ""),
                reason=request.data.get("reason", ""),
                policy_section=request.data.get("policy_section", ""),
                evidence=request.data.get("evidence", ""), actor=request.user)
        except service.GovernanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"status": action.to_status}, status=200)


class StaffAppealView(_StaffView):
    def get(self, request):
        self._staff(request)
        return Response({"summary": service.summary(), "appeals": [
            {"id": a.id, "organization": a.organization_id, "reason": a.reason,
             "status": a.status, "outcome": a.outcome}
            for a in Appeal.objects.all()[:200]]})

    def post(self, request, pk):
        self._staff(request)
        appeal = get_object_or_404(Appeal, pk=pk)
        try:
            service.decide_appeal(
                appeal, request.data.get("outcome", ""),
                resolution=request.data.get("resolution", ""), reviewer=request.user)
        except service.GovernanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"status": appeal.status, "outcome": appeal.outcome})
