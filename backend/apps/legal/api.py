"""Legal API (spec §56).

Public: read the current published documents and one document's content/versions.
Authenticated: record an acceptance (durable, versioned, with IP/UA captured),
list your own acceptances, see what's pending. Staff-only: author and publish.
Legal records are sensitive — a user only ever sees their own acceptances.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.legal import service
from apps.legal.models import ConsentType, LegalDocument
from apps.legal.registry import DOCUMENT_TYPES, JURISDICTIONS


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _doc_summary(d: LegalDocument) -> dict:
    return {
        "slug": d.slug, "document_type": d.document_type, "title": d.title,
        "jurisdiction": d.jurisdiction, "language": d.language, "version": d.version,
        "effective_at": d.effective_at.isoformat() if d.effective_at else None,
        "requires_acceptance": d.requires_acceptance,
    }


def _doc_full(d: LegalDocument) -> dict:
    return {**_doc_summary(d), "content": d.content, "content_sha256": d.content_sha256,
            "published_at": d.published_at.isoformat() if d.published_at else None,
            "change_summary": d.change_summary}


class DocumentListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        juris = request.query_params.get("jurisdiction", "global")
        lang = request.query_params.get("language", "en")
        docs = service.published_documents(jurisdiction=juris, language=lang)
        return Response({
            "jurisdiction": juris, "language": lang,
            "documents": [_doc_summary(d) for d in docs],
        })


class DocumentDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        doc = get_object_or_404(LegalDocument, slug=slug)
        # Only published/superseded/archived content is viewable publicly; drafts
        # and in-review documents are never exposed to customers.
        if doc.status in ("draft", "under_review", "approved", "scheduled"):
            raise PermissionDenied("Document not available.")
        return Response(_doc_full(doc))


class DocumentVersionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, document_type):
        juris = request.query_params.get("jurisdiction", "global")
        lang = request.query_params.get("language", "en")
        return Response({
            "document_type": document_type,
            "versions": [{"version": d.version, "status": d.status, "slug": d.slug,
                          "published_at": d.published_at.isoformat() if d.published_at else None,
                          "change_summary": d.change_summary}
                         for d in service.versions(document_type, jurisdiction=juris, language=lang)],
        })


class AcceptanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"acceptances": [
            {"document_type": a.document_type, "version": a.version, "slug": a.document.slug,
             "consent_type": a.consent_type, "accepted_at": a.accepted_at.isoformat()}
            for a in service.acceptance_history(request.user)]})

    def post(self, request):
        doc = get_object_or_404(LegalDocument, slug=request.data.get("document", ""))
        organization = None
        org_id = request.data.get("organization")
        if org_id:
            from apps.organizations.access import organizations_for
            organization = get_object_or_404(organizations_for(request.user), pk=org_id)
        consent = request.data.get("consent_type", ConsentType.MANDATORY)
        if consent not in ConsentType.values:
            consent = ConsentType.MANDATORY
        try:
            service.record_acceptance(
                request.user, doc, organization=organization, consent_type=consent,
                method=request.data.get("method", "clickwrap"),
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                country=request.data.get("country", ""))
        except service.LegalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"recorded": True}, status=201)


class PendingAcceptanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        juris = request.query_params.get("jurisdiction", "global")
        pending = service.pending_acceptances(request.user, jurisdiction=juris)
        return Response({"pending": [_doc_summary(d) for d in pending]})


# --- staff authoring ---------------------------------------------------------

class _StaffView(APIView):
    permission_classes = [IsAuthenticated]

    def _require_staff(self, request):
        if not request.user.is_staff:
            raise PermissionDenied("Legal administration is staff-only.")


class AdminDocumentView(_StaffView):
    def get(self, request):
        self._require_staff(request)
        return Response({
            "document_types": [{"code": c, "label": l} for c, l in DOCUMENT_TYPES.items()],
            "jurisdictions": [{"code": c, "label": l} for c, l in JURISDICTIONS.items()],
            "documents": [{"id": d.id, **_doc_summary(d), "status": d.status}
                          for d in LegalDocument.objects.all()[:500]],
        })

    def post(self, request):
        self._require_staff(request)
        d = request.data
        try:
            doc = service.create_draft(
                document_type=d.get("document_type", ""), title=d.get("title", ""),
                version=d.get("version", ""), content=d.get("content", ""),
                jurisdiction=d.get("jurisdiction", "global"),
                language=d.get("language", "en"),
                requires_acceptance=d.get("requires_acceptance", False),
                acceptance_scope=d.get("acceptance_scope", "user"),
                change_summary=d.get("change_summary", ""), user=request.user)
        except service.LegalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"id": doc.id, **_doc_summary(doc), "status": doc.status}, status=201)


class AdminActionView(_StaffView):
    def post(self, request, pk):
        self._require_staff(request)
        doc = get_object_or_404(LegalDocument, pk=pk)
        action = request.data.get("action")
        actions = {"submit": service.submit_for_review, "approve": service.approve,
                   "publish": service.publish, "archive": service.archive}
        if action == "edit":
            try:
                service.update_draft(doc, user=request.user, **{
                    k: request.data[k] for k in
                    ("title", "content", "change_summary", "requires_acceptance")
                    if k in request.data})
            except (service.LegalError, ValueError) as exc:
                return Response({"detail": str(exc)}, status=400)
        elif action in actions:
            try:
                actions[action](doc, user=request.user)
            except service.LegalError as exc:
                return Response({"detail": str(exc)}, status=400)
        else:
            return Response({"detail": f"Unknown action '{action}'."}, status=400)
        doc.refresh_from_db()
        return Response({"id": doc.id, **_doc_summary(doc), "status": doc.status})


class JurisdictionView(APIView):
    """Public: the customer-facing notices configured for a jurisdiction. Honest —
    returns configured:false when counsel hasn't set anything (spec §5)."""
    permission_classes = [AllowAny]

    def get(self, request, jurisdiction):
        return Response(service.jurisdiction_notices(jurisdiction))


class LawRequestView(_StaffView):
    """Government / legal data requests (spec §71). Staff-only and sensitive;
    customer data is never auto-disclosed."""

    def get(self, request):
        self._require_staff(request)
        from apps.legal.models import LawEnforcementRequest
        return Response({"requests": [
            {"id": r.id, "authority": r.authority, "jurisdiction": r.jurisdiction,
             "request_type": r.request_type, "decision": r.decision,
             "disclosed": r.disclosed, "received_at": r.received_at.isoformat()}
            for r in LawEnforcementRequest.objects.all()[:200]]})

    def post(self, request):
        self._require_staff(request)
        try:
            req = service.log_law_request(
                authority=request.data.get("authority", ""),
                jurisdiction=request.data.get("jurisdiction", ""),
                request_type=request.data.get("request_type", ""),
                data_requested=request.data.get("data_requested", ""),
                legal_basis=request.data.get("legal_basis", ""), user=request.user)
        except service.LegalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"id": req.id, "decision": req.decision}, status=201)
