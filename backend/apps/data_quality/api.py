"""Data-quality API (spec §9) — one source of truth web + mobile consume.

Read datasets, rules and the latest check results; add datasets/rules (owner/
admin); run a check against supplied rows (any member — the runtime call). A
check produces real counts, never an estimate.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.data_quality import service
from apps.data_quality.engine import CHECKS
from apps.data_quality.models import Dataset, DataQualityRule
from apps.projects.access import project_for_read, require_manageable_project


def _rule_dict(r: DataQualityRule) -> dict:
    return {"id": r.id, "field": r.field, "check": r.check_type, "params": r.params,
            "severity": r.severity, "enabled": r.enabled}


def _dataset_dict(ds: Dataset) -> dict:
    last = ds.runs.first()
    return {
        "id": ds.id, "key": ds.key, "name": ds.name, "description": ds.description,
        "rules": [_rule_dict(r) for r in ds.rules.all()],
        "latest": {"score": last.score, "rows": last.rows, "failing": last.failing,
                   "results": last.results, "at": last.created_at.isoformat()}
        if last else None,
    }


def _payload(project) -> dict:
    return {
        "summary": service.summary(project),
        "datasets": [_dataset_dict(d) for d in project.datasets.all()],
        "checks": [{"key": k, "label": v} for k, v in CHECKS.items()],
    }


class DataQualityView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))


class DatasetCreateView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            service.add_dataset(project, key=request.data.get("key", ""),
                               name=request.data.get("name", ""),
                               description=request.data.get("description", ""),
                               user=request.user)
        except service.DataQualityError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_payload(project), status=201)


class RuleCreateView(APIView):
    def _dataset(self, request, pk, *, manage=True):
        ds = get_object_or_404(Dataset.objects.select_related("project"), pk=pk)
        require_manageable_project(request.user, ds.project_id)
        return ds

    def post(self, request, pk):
        ds = self._dataset(request, pk)
        try:
            service.add_rule(ds, field=request.data.get("field", ""),
                            check=request.data.get("check", ""),
                            params=request.data.get("params") or {},
                            severity=request.data.get("severity", "error"),
                            user=request.user)
        except service.DataQualityError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_dataset_dict(ds), status=201)


class CheckView(APIView):
    """Run the dataset's rules against supplied rows — the runtime call an app or
    import makes. Returns the real results of the check."""

    def post(self, request, pk):
        ds = get_object_or_404(Dataset.objects.select_related("project"), pk=pk)
        project_for_read(request.user, ds.project_id)   # any member (runtime)
        try:
            run = service.check(ds, request.data.get("rows"), user=request.user)
        except service.DataQualityError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"score": run.score, "rows": run.rows,
                         "failing": run.failing, "results": run.results})
