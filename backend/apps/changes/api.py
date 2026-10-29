"""Change-request API (mobile/API client).

"Request a change to my app" over apps.changes services — the same
REQUEST → ANALYZE → PLAN → ESTIMATE → APPROVE → IMPLEMENT flow the web uses,
no logic duplicated. Reads need org membership; approve/implement/rollback need
owner/admin.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.changes import service
from apps.changes.impact import analyze_impact
from apps.changes.models import ChangeRequest
from apps.organizations.access import manageable_organizations_for, organizations_for
from apps.projects.access import project_for_read, require_manageable_project


def _change_dict(c: ChangeRequest) -> dict:
    return {
        "id": c.id,
        "project": c.project_id,
        "description": c.description,
        "status": c.status,
        "status_display": c.get_status_display(),
        "plan": c.plan,
        "estimate": c.estimate,
        "requires_approval": c.requires_approval,
        "approved": c.approved,
        "risk": c.risk,
        "impact": analyze_impact(c),
        "can_rollback": c.can_rollback,
        "result": c.result,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


class ChangeListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response([_change_dict(c) for c in project.changes.all()])

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        description = (request.data.get("description") or "").strip()
        if not description:
            return Response({"description": ["Describe the change you want."]},
                            status=status.HTTP_400_BAD_REQUEST)
        change = service.create_change(project, description, request.user)
        service.build_plan(change)  # analyze → impact → plan → estimate → approval gate
        change.refresh_from_db()
        return Response(_change_dict(change), status=status.HTTP_201_CREATED)


class _ChangeActionView(APIView):
    manage = True

    def change(self, request, pk):
        change = get_object_or_404(ChangeRequest, pk=pk)
        org = change.project.organization
        if org not in organizations_for(request.user):
            from django.http import Http404

            raise Http404
        if self.manage and org not in manageable_organizations_for(request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Owner or admin required.")
        return change


class ChangeDetailView(_ChangeActionView):
    manage = False

    def get(self, request, pk):
        return Response(_change_dict(self.change(request, pk)))


class ChangeApproveView(_ChangeActionView):
    def post(self, request, pk):
        change = self.change(request, pk)
        service.approve(change, request.user)
        change.refresh_from_db()
        return Response(_change_dict(change))


class ChangeImplementView(_ChangeActionView):
    def post(self, request, pk):
        change = self.change(request, pk)
        service.implement(change)
        change.refresh_from_db()
        return Response(_change_dict(change))


class ChangeRollbackView(_ChangeActionView):
    def post(self, request, pk):
        change = self.change(request, pk)
        service.rollback(change)
        change.refresh_from_db()
        return Response(_change_dict(change))
