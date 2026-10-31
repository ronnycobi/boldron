"""Explain-my-application API (spec §29) — read-only, tenant-isolated and
customer-safe. With ?node=<id> it explains one part of the app instead."""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.explain.explain import explain_application, explain_part
from apps.projects.access import project_for_read


class ExplainView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        node_id = request.query_params.get("node")
        if node_id:
            part = explain_part(project, node_id)
            if part is None:
                return Response({"detail": "Unknown part."}, status=404)
            return Response(part)
        return Response(explain_application(project))
