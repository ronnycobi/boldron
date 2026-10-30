"""Acceptance-criteria API (spec §3) — one source of truth web + mobile consume.

Read a project's criteria + honest acceptance status; add a criterion, import the
ones embedded in requirements, and verify (owner/admin). The AI never marks a
criterion met — verification is an explicit human action.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.acceptance import service
from apps.acceptance.models import AcceptanceCriterion
from apps.projects.access import project_for_read, require_manageable_project


def _verifier(u) -> str | None:
    if not u:
        return None
    name = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
    return name or getattr(u, "email", None)


def _criterion_dict(c: AcceptanceCriterion) -> dict:
    return {
        "id": c.id,
        "statement": c.statement,
        "status": c.status,
        "status_label": c.get_status_display(),
        "requirement": c.requirement_id,
        "requirement_title": c.requirement_title,
        "note": c.note,
        "verified_by": _verifier(c.verified_by),
        "verified_at": c.verified_at.isoformat() if c.verified_at else None,
        "order": c.order,
    }


def _payload(project) -> dict:
    return {
        "summary": service.summary(project),
        "criteria": [_criterion_dict(c) for c in project.acceptance_criteria.all()],
    }


class AcceptanceListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        requirement = None
        req_id = request.data.get("requirement")
        if req_id:
            requirement = get_object_or_404(
                project.context_entries, pk=req_id)
        try:
            service.add(project, request.data.get("statement", ""),
                        requirement=requirement, user=request.user)
        except service.AcceptanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_payload(project), status=201)


class AcceptanceImportView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        created = service.import_from_requirements(project, user=request.user)
        return Response({**_payload(project), "imported": created})


class AcceptanceVerifyView(APIView):
    def post(self, request, pk):
        criterion = get_object_or_404(
            AcceptanceCriterion.objects.select_related("project"), pk=pk)
        require_manageable_project(request.user, criterion.project_id)
        try:
            service.verify(criterion, request.data.get("status", ""),
                           note=request.data.get("note", ""), user=request.user)
        except service.AcceptanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_criterion_dict(criterion))
