"""Performance API (spec §41) — one source of truth web + mobile consume.

Record real timing samples (any member — the runtime call an app/probe makes);
read the honest report; set budgets (owner/admin).
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.performance import service
from apps.projects.access import project_for_read, require_manageable_project


class PerformanceView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response({
            "summary": service.summary(project),
            "report": service.report(project),
            "budgets": [{"label": b.label, "threshold_ms": b.threshold_ms}
                        for b in project.perf_budgets.all()],
        })


class SampleView(APIView):
    def post(self, request, project_pk):
        project = project_for_read(request.user, project_pk)   # runtime
        try:
            n = service.record_samples(project, request.data.get("samples"),
                                       user=request.user)
        except service.PerformanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"recorded": n}, status=201)


class BudgetView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            service.set_budget(project, label=request.data.get("label", "*"),
                               threshold_ms=request.data.get("threshold_ms"),
                               user=request.user)
        except service.PerformanceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"budgets": [{"label": b.label, "threshold_ms": b.threshold_ms}
                                     for b in project.perf_budgets.all()]})
