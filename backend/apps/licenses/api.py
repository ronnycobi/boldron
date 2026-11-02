"""License API (spec §12) — per-project, tenant-isolated.

Read the license report + attribution, import dependencies from the project's
captured manifest, and record a dependency's license (owner/admin).
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.licenses import service
from apps.projects.access import project_for_read, require_manageable_project


class LicenseReportView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response({**service.report(project),
                         "attribution": service.attribution(project)})

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        action = request.data.get("action")
        if action == "import":
            n = service.import_from_context(project)
            return Response({**service.report(project), "imported": n})
        if action == "record":
            try:
                service.record_dependency(
                    project, package=request.data.get("package", ""),
                    version=request.data.get("version", ""),
                    license=request.data.get("license", ""),
                    source=request.data.get("source", ""), user=request.user)
            except service.LicenseError as exc:
                return Response({"detail": str(exc)}, status=400)
            return Response(service.report(project), status=201)
        return Response({"detail": "Unknown action."}, status=400)
