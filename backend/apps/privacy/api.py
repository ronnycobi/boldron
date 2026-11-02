"""Privacy API (spec §17-19, §56, §75).

Users submit and track their own requests, and download a secrets-safe export of
their data. Privacy records are sensitive: a user only ever sees their own, and
the staff queue is staff-only.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.privacy import service
from apps.privacy.models import PrivacyRequest, RequestStatus, RequestType


def _req_dict(r: PrivacyRequest, *, events=False) -> dict:
    data = {
        "id": r.id, "request_type": r.request_type,
        "type_label": r.get_request_type_display(),
        "status": r.status, "status_label": r.get_status_display(),
        "jurisdiction": r.jurisdiction, "details": r.details,
        "deadline": r.deadline.isoformat() if r.deadline else None,
        "created_at": r.created_at.isoformat(),
        "resolution": r.resolution,
    }
    if events:
        data["events"] = [{"kind": e.kind, "status": e.status, "note": e.note,
                           "at": e.created_at.isoformat()} for e in r.events.all()]
    return data


class PrivacyRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "types": [{"key": t.value, "label": t.label} for t in RequestType],
            "requests": [_req_dict(r) for r in request.user.privacy_requests.all()],
        })

    def post(self, request):
        organization = None
        org_id = request.data.get("organization")
        if org_id:
            from apps.organizations.access import organizations_for
            organization = get_object_or_404(organizations_for(request.user), pk=org_id)
        try:
            req = service.submit(
                request.user, request.data.get("request_type", ""),
                organization=organization,
                jurisdiction=request.data.get("jurisdiction", ""),
                details=request.data.get("details", ""))
        except service.PrivacyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_req_dict(req, events=True), status=201)


class PrivacyRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        req = get_object_or_404(PrivacyRequest, pk=pk)
        if req.user_id != request.user.id:
            raise PermissionDenied("Not your request.")
        return Response(_req_dict(req, events=True))


class PrivacyExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Download a secrets-safe export of the user's own data."""
        return Response(service.build_export(request.user))


class PrivacyAdminView(APIView):
    """Staff queue (spec §75 — legal records are staff-only, never on tenant APIs)."""
    permission_classes = [IsAuthenticated]

    def _staff(self, request):
        if not request.user.is_staff:
            raise PermissionDenied("Privacy administration is staff-only.")

    def get(self, request):
        self._staff(request)
        return Response({
            "summary": service.summary(),
            "requests": [_req_dict(r) for r in PrivacyRequest.objects.all()[:300]],
        })

    def post(self, request, pk):
        self._staff(request)
        req = get_object_or_404(PrivacyRequest, pk=pk)
        action = request.data.get("action")
        try:
            if action == "transition":
                service.transition(req, request.data.get("status", ""),
                                   note=request.data.get("note", ""), actor=request.user)
            elif action == "resolve":
                service.resolve(req, resolution=request.data.get("resolution", ""),
                               status=request.data.get("status", RequestStatus.COMPLETED),
                               actor=request.user)
            else:
                return Response({"detail": "Unknown action."}, status=400)
        except service.PrivacyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_req_dict(req, events=True))
