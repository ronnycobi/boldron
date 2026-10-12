"""Project backups API (mobile/API client) — restore points (spec §13).

Over apps.backups services: create a snapshot before a big change, restore any
time. Code restore only — never implies it reverses database migrations.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.backups.models import ProjectBackup
from apps.backups.service import BackupError, create_backup, restore_backup
from apps.organizations.access import manageable_organizations_for, organizations_for
from apps.projects.access import project_for_read, require_manageable_project


def _backup_dict(b: ProjectBackup) -> dict:
    return {
        "id": b.id,
        "label": b.label,
        "commit_sha": b.commit_sha,
        "created_by": getattr(b.created_by, "display_name", "") or "",
        "created_at": b.created_at.isoformat(),
    }


class BackupListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response([_backup_dict(b) for b in project.backups.all()])

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            backup = create_backup(
                project, label=(request.data.get("label") or "Snapshot").strip(),
                created_by=request.user,
            )
        except BackupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_backup_dict(backup), status=status.HTTP_201_CREATED)


class BackupRestoreView(APIView):
    def post(self, request, pk):
        backup = get_object_or_404(ProjectBackup, pk=pk)
        if backup.project.organization not in organizations_for(request.user):
            from django.http import Http404

            raise Http404
        if backup.project.organization not in manageable_organizations_for(request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Owner or admin required.")
        try:
            restore_backup(backup, actor=request.user)
        except BackupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "detail": "Project files were restored to this snapshot. "
                          "Note: this restores code, not database data.",
                **_backup_dict(backup),
            }
        )
