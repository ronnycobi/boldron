from django.urls import path

from apps.privacy.api import (
    PrivacyAdminView,
    PrivacyExportView,
    PrivacyRequestDetailView,
    PrivacyRequestView,
)

app_name = "privacy_api"

urlpatterns = [
    path("privacy/requests/", PrivacyRequestView.as_view(), name="requests"),
    path("privacy/requests/<int:pk>/", PrivacyRequestDetailView.as_view(), name="request"),
    path("privacy/export/", PrivacyExportView.as_view(), name="export"),
    path("privacy/admin/requests/", PrivacyAdminView.as_view(), name="admin"),
    path("privacy/admin/requests/<int:pk>/", PrivacyAdminView.as_view(), name="admin_action"),
]
