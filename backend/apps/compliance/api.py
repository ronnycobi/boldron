"""Compliance API (spec §16) — one source of truth web + mobile consume.

Read controls + per-framework score; seed a framework and attest controls
(owner/admin). Platform-provided controls are evidenced automatically; everything
else requires a human attestation with evidence — nothing is auto-claimed met.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.compliance import service
from apps.compliance.catalog import frameworks
from apps.compliance.models import ComplianceControl
from apps.projects.access import project_for_read, require_manageable_project


def _control_dict(c: ComplianceControl) -> dict:
    return {
        "id": c.id, "framework": c.framework, "code": c.code, "title": c.title,
        "description": c.description, "status": c.status,
        "status_label": c.get_status_display(), "evidence": c.evidence,
        "auto": c.auto,
        "attested_by": getattr(c.attested_by, "email", None),
        "attested_at": c.attested_at.isoformat() if c.attested_at else None,
    }


def _payload(project) -> dict:
    return {
        "score": service.score(project),
        "controls": [_control_dict(c) for c in project.compliance_controls.all()],
        "frameworks": frameworks(),
    }


class ComplianceView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))


class ComplianceSeedView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            created = service.seed_framework(
                project, request.data.get("framework", ""), user=request.user)
        except service.ComplianceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({**_payload(project), "created": created})


class ComplianceAttestView(APIView):
    def post(self, request, pk):
        control = get_object_or_404(
            ComplianceControl.objects.select_related("project"), pk=pk)
        require_manageable_project(request.user, control.project_id)
        try:
            service.attest(control, request.data.get("status", ""),
                           evidence=request.data.get("evidence", ""), user=request.user)
        except service.ComplianceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_control_dict(control))
