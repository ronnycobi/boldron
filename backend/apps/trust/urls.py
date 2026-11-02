from django.urls import path

from apps.trust.api import (
    DisclosureView,
    ReportAdminView,
    SecurityOverviewView,
    SubprocessorView,
)

app_name = "trust"

urlpatterns = [
    path("trust/subprocessors/", SubprocessorView.as_view(), name="subprocessors"),
    path("trust/security/", SecurityOverviewView.as_view(), name="security"),
    path("trust/disclosure/", DisclosureView.as_view(), name="disclosure"),
    path("trust/admin/reports/", ReportAdminView.as_view(), name="reports"),
    path("trust/admin/reports/<int:pk>/", ReportAdminView.as_view(), name="report_action"),
]
