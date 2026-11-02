from django.urls import path

from apps.legal.api import (
    AcceptanceView,
    JurisdictionView,
    LawRequestView,
    AdminActionView,
    AdminDocumentView,
    DocumentDetailView,
    DocumentListView,
    DocumentVersionsView,
    PendingAcceptanceView,
)

app_name = "legal"

urlpatterns = [
    path("legal/documents/", DocumentListView.as_view(), name="documents"),
    path("legal/documents/<slug:slug>/", DocumentDetailView.as_view(), name="document"),
    path("legal/types/<str:document_type>/versions/",
         DocumentVersionsView.as_view(), name="versions"),
    path("legal/acceptances/", AcceptanceView.as_view(), name="acceptances"),
    path("legal/pending/", PendingAcceptanceView.as_view(), name="pending"),
    path("legal/jurisdictions/<str:jurisdiction>/", JurisdictionView.as_view(), name="jurisdiction"),
    path("legal/admin/law-requests/", LawRequestView.as_view(), name="law_requests"),
    # staff authoring
    path("legal/admin/documents/", AdminDocumentView.as_view(), name="admin_documents"),
    path("legal/admin/documents/<int:pk>/", AdminActionView.as_view(), name="admin_action"),
]
