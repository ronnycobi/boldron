"""Automations API (spec §10-11) — one source of truth web + mobile consume.

Read automations, their recent runs, and the available triggers/actions; create,
edit, change status, and test-run (owner/admin). Test runs honour conditions and
record honest per-action outcomes — nothing is faked.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.automations import engine, service
from apps.automations.actions import ACTIONS
from apps.automations.models import Workflow
from apps.automations.triggers import TRIGGERS
from apps.projects.access import project_for_read, require_manageable_project


def _run_dict(r) -> dict:
    return {"id": r.id, "trigger": r.trigger, "status": r.status,
            "results": r.results, "created_at": r.created_at.isoformat()}


def _wf_dict(wf, *, runs=False) -> dict:
    data = {
        "id": wf.id, "name": wf.name, "description": wf.description,
        "trigger": wf.trigger,
        "trigger_label": TRIGGERS.get(wf.trigger, {}).get("label", wf.trigger),
        "conditions": wf.conditions or [], "actions": wf.actions or [],
        "status": wf.status, "status_label": wf.get_status_display(),
        "run_count": wf.run_count,
        "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
    }
    if runs:
        data["runs"] = [_run_dict(r) for r in wf.runs.all()[:20]]
    return data


def _catalog() -> dict:
    return {
        "triggers": [{"key": k, "label": v["label"], "description": v["description"],
                      "facts": v["facts"]} for k, v in TRIGGERS.items()],
        "actions": [{"key": k, "label": v["label"], "params": v["params"]}
                    for k, v in ACTIONS.items()],
    }


class AutomationListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response({
            "summary": service.summary(project),
            "automations": [_wf_dict(w) for w in project.automations.all()],
            "catalog": _catalog(),
        })

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        try:
            wf = service.create(
                project, name=d.get("name", ""), trigger=d.get("trigger", ""),
                actions=d.get("actions", []), description=d.get("description", ""),
                conditions=d.get("conditions", []), user=request.user)
        except service.AutomationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_wf_dict(wf, runs=True), status=201)


class AutomationDetailView(APIView):
    def _wf(self, request, pk, *, manage=False):
        wf = get_object_or_404(Workflow.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, wf.project_id)
        else:
            project_for_read(request.user, wf.project_id)
        return wf

    def get(self, request, pk):
        return Response(_wf_dict(self._wf(request, pk), runs=True))

    def patch(self, request, pk):
        wf = self._wf(request, pk, manage=True)
        try:
            service.update(wf, user=request.user, **request.data)
        except service.AutomationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_wf_dict(wf, runs=True))


class AutomationStatusView(AutomationDetailView):
    def post(self, request, pk):
        wf = self._wf(request, pk, manage=True)
        try:
            service.set_status(wf, request.data.get("status", ""), user=request.user)
        except service.AutomationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_wf_dict(wf, runs=True))


class AutomationRunView(AutomationDetailView):
    """Test-run an automation against supplied facts — a real execution."""

    def post(self, request, pk):
        wf = self._wf(request, pk, manage=True)
        facts = request.data.get("facts") or {}
        if not isinstance(facts, dict):
            return Response({"detail": "'facts' must be an object."}, status=400)
        run = engine.run_now(wf, facts, user=request.user)
        return Response(_run_dict(run))
