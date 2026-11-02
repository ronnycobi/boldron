"""Trust Center API (spec §26, §28, §29).

Public: the subprocessor register, the honest security overview, disclosure info,
and a private vulnerability-report submission. Staff-only: manage subprocessors
and triage reports (reports are never public).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trust import service
from apps.trust.models import Subprocessor, VulnerabilityReport


def _sp(sp: Subprocessor) -> dict:
    return {"name": sp.name, "category": sp.category,
            "category_label": sp.get_category_display(), "service": sp.service,
            "data_processed": sp.data_processed, "purpose": sp.purpose,
            "location": sp.location, "transfer_mechanism": sp.transfer_mechanism,
            "status": sp.status}


class SubprocessorView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"subprocessors": [_sp(s) for s in service.active_subprocessors()]})


class SecurityOverviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(service.security_overview())


class DisclosureView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(service.disclosure_info())

    def post(self, request):
        try:
            report = service.submit_vulnerability(
                summary=request.data.get("summary", ""),
                details=request.data.get("details", ""),
                reporter_email=request.data.get("reporter_email", ""),
                severity_estimate=request.data.get("severity_estimate", ""))
        except service.TrustError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"received": True, "id": report.id}, status=201)


class ReportAdminView(APIView):
    """Staff-only triage of private vulnerability reports."""
    permission_classes = [IsAuthenticated]

    def _staff(self, request):
        if not request.user.is_staff:
            raise PermissionDenied("Staff only.")

    def get(self, request):
        self._staff(request)
        return Response({"reports": [
            {"id": r.id, "summary": r.summary, "severity": r.severity_estimate,
             "status": r.status, "created_at": r.created_at.isoformat()}
            for r in VulnerabilityReport.objects.all()[:200]]})

    def post(self, request, pk):
        self._staff(request)
        report = get_object_or_404(VulnerabilityReport, pk=pk)
        try:
            service.set_report_status(report, request.data.get("status", ""),
                                      resolution=request.data.get("resolution", ""),
                                      user=request.user)
        except service.TrustError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"status": report.status})
