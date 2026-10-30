"""Incident API (spec §20, §24) — one source of truth web + mobile consume.

Read incidents + their timeline; open an incident, add notes, transition status
(owner/admin). Resolution is an explicit action — nothing auto-resolves.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.incidents import service
from apps.incidents.models import Incident
from apps.projects.access import project_for_read, require_manageable_project


def _event_dict(e) -> dict:
    return {"kind": e.kind, "status": e.status, "message": e.message,
            "created_at": e.created_at.isoformat()}


def _incident_dict(i, *, events=False) -> dict:
    data = {
        "id": i.id, "title": i.title, "severity": i.severity, "status": i.status,
        "source": i.source, "is_open": i.is_open, "detail": i.detail,
        "resolution": i.resolution, "postmortem": i.postmortem,
        "deployment": i.deployment_id,
        "detected_at": i.detected_at.isoformat(),
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "duration_seconds": i.duration_seconds,
    }
    if events:
        data["timeline"] = [_event_dict(e) for e in i.events.all()]
    return data


class IncidentListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response({
            "summary": service.summary(project),
            "incidents": [_incident_dict(i) for i in project.incidents.all()[:100]],
        })

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        try:
            incident = service.open_incident(
                project, title=d.get("title", ""), severity=d.get("severity", "medium"),
                detail=d.get("detail", ""), user=request.user)
        except service.IncidentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_incident_dict(incident, events=True), status=201)


class _IncidentView(APIView):
    def incident(self, request, pk, *, manage=False):
        incident = get_object_or_404(Incident.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, incident.project_id)
        else:
            project_for_read(request.user, incident.project_id)
        return incident


class IncidentDetailView(_IncidentView):
    def get(self, request, pk):
        return Response(_incident_dict(self.incident(request, pk), events=True))


class IncidentTransitionView(_IncidentView):
    def post(self, request, pk):
        incident = self.incident(request, pk, manage=True)
        try:
            service.transition(incident, request.data.get("status", ""),
                               note=request.data.get("note", ""), user=request.user)
            if request.data.get("resolution") or request.data.get("postmortem"):
                service.set_resolution(
                    incident, resolution=request.data.get("resolution", ""),
                    postmortem=request.data.get("postmortem", ""), user=request.user)
        except service.IncidentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_incident_dict(incident, events=True))


class IncidentNoteView(_IncidentView):
    def post(self, request, pk):
        incident = self.incident(request, pk, manage=True)
        try:
            service.add_note(incident, request.data.get("text", ""), user=request.user)
        except service.IncidentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_incident_dict(incident, events=True))
