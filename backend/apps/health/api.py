"""Project Health API (spec §30) — one source of truth web + mobile consume.

Read-only, tenant-isolated, customer-safe: the composed health score and its
per-pillar breakdown, derived live from the project's real ledgers.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.health.score import health_score
from apps.projects.access import project_for_read


class ProjectHealthView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(health_score(project))
