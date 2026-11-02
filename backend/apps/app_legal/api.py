"""Application-legal API (spec §62-68) — per-project, tenant-isolated.

Read the privacy scan, consistency findings, compliance check and existing
generated drafts; generate a draft (owner/admin); and ask which documents a
described change should trigger a review of.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.app_legal import analysis, generator
from apps.app_legal.models import GeneratedLegalDoc
from apps.projects.access import project_for_read, require_manageable_project


def _overview(project) -> dict:
    return {
        "data_types": analysis.scan_data_types(project),
        "consistency": analysis.consistency_findings(project),
        "compliance": analysis.compliance_check(project),
        "generated": [{"doc_type": d.doc_type, "reviewed": d.reviewed,
                       "created_at": d.created_at.isoformat()}
                      for d in project.generated_legal_docs.all()],
        "generatable": generator.GENERATABLE,
    }


class AppLegalView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response(_overview(project))


class GenerateView(APIView):
    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        try:
            doc = generator.generate(project, request.data.get("doc_type", ""),
                                     user=request.user)
        except generator.GeneratorError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"doc_type": doc.doc_type, "content": doc.content,
                         "disclaimer": doc.disclaimer}, status=201)


class ReviewTriggerView(APIView):
    def post(self, request, project_pk):
        project_for_read(request.user, project_pk)
        docs = analysis.review_triggers(request.data.get("change", ""))
        return Response({"review": docs,
                         "note": "These documents may need review for this change. "
                                 "Confirm with legal counsel." if docs else
                                 "No legal review obviously triggered by this change."})
