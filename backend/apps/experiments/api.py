"""Experiments API (spec §20) — one source of truth web + mobile consume.

Read experiments + real results; create and start/stop (owner/admin). Assign a
subject and record a conversion (any member — the runtime calls an app makes).
Results are real counts with an honest significance verdict.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.experiments import service
from apps.experiments.models import Experiment
from apps.projects.access import project_for_read, require_manageable_project


def _exp_dict(e: Experiment, *, results=False) -> dict:
    data = {
        "id": e.id, "key": e.key, "name": e.name, "description": e.description,
        "status": e.status, "status_label": e.get_status_display(),
        "variants": e.variants, "metric": e.metric,
    }
    if results:
        data["results"] = service.results(e)
    return data


class ExperimentListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response({
            "summary": service.summary(project),
            "experiments": [_exp_dict(e, results=True)
                            for e in project.experiments.all()],
        })

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        try:
            exp = service.create(
                project, key=d.get("key", ""), variants=d.get("variants", []),
                name=d.get("name", ""), description=d.get("description", ""),
                metric=d.get("metric", "conversion"), user=request.user)
        except service.ExperimentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_exp_dict(exp, results=True), status=201)


class ExperimentDetailView(APIView):
    def _exp(self, request, pk, *, manage=False):
        exp = get_object_or_404(Experiment.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, exp.project_id)
        else:
            project_for_read(request.user, exp.project_id)
        return exp

    def get(self, request, pk):
        return Response(_exp_dict(self._exp(request, pk), results=True))


class ExperimentStatusView(ExperimentDetailView):
    def post(self, request, pk):
        exp = self._exp(request, pk, manage=True)
        try:
            service.set_status(exp, request.data.get("status", ""), user=request.user)
        except service.ExperimentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_exp_dict(exp, results=True))


class ExperimentAssignView(ExperimentDetailView):
    """Assign a subject to a variant — the runtime call an app makes. Returns the
    variant, or null when the experiment isn't running (honest — no assignment)."""

    def post(self, request, pk):
        exp = self._exp(request, pk)   # any member (runtime)
        variant = service.assign(exp, request.data.get("subject", ""))
        return Response({"variant": variant, "running": exp.is_running})


class ExperimentConvertView(ExperimentDetailView):
    def post(self, request, pk):
        exp = self._exp(request, pk)
        recorded = service.convert(exp, request.data.get("subject", ""))
        return Response({"recorded": recorded})
