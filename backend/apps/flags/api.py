"""Feature-flags API (spec §19) — one source of truth web + mobile consume.

Read flags + summary; create, edit, toggle, archive (owner/admin). Evaluate the
whole set for a context (any member) — the deterministic call an app makes to
decide what's on.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.flags import service
from apps.flags.models import FeatureFlag
from apps.projects.access import project_for_read, require_manageable_project


def _flag_dict(f: FeatureFlag) -> dict:
    return {
        "id": f.id, "key": f.key, "name": f.name, "description": f.description,
        "enabled": f.enabled, "rollout": f.rollout,
        "conditions": f.conditions or [], "targeted": f.is_targeted,
        "archived": f.archived,
    }


def _payload(project) -> dict:
    return {
        "summary": service.summary(project),
        "flags": [_flag_dict(f) for f in project.feature_flags.filter(archived=False)],
    }


class FlagListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_payload(project))

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        d = request.data
        try:
            flag = service.create(
                project, key=d.get("key", ""), name=d.get("name", ""),
                description=d.get("description", ""), enabled=d.get("enabled", False),
                rollout=d.get("rollout", 100), conditions=d.get("conditions", []),
                user=request.user)
        except service.FlagError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_flag_dict(flag), status=201)


class FlagDetailView(APIView):
    def _flag(self, request, pk, *, manage=False):
        flag = get_object_or_404(FeatureFlag.objects.select_related("project"), pk=pk)
        if manage:
            require_manageable_project(request.user, flag.project_id)
        else:
            project_for_read(request.user, flag.project_id)
        return flag

    def patch(self, request, pk):
        flag = self._flag(request, pk, manage=True)
        try:
            service.update(flag, user=request.user, **request.data)
        except service.FlagError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_flag_dict(flag))


class FlagToggleView(FlagDetailView):
    def post(self, request, pk):
        flag = self._flag(request, pk, manage=True)
        service.toggle(flag, bool(request.data.get("enabled")), user=request.user)
        return Response(_flag_dict(flag))


class FlagEvaluateView(APIView):
    """Evaluate all of a project's flags for a context — the deterministic read an
    app performs to decide what to show."""

    def post(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        context = request.data.get("context") or {}
        if not isinstance(context, dict):
            return Response({"detail": "'context' must be an object."}, status=400)
        return Response({"flags": service.evaluate_all(project, context)})
