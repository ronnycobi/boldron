from django.urls import path

from apps.licenses.api import LicenseReportView

app_name = "licenses"

urlpatterns = [
    path("projects/<int:project_pk>/licenses/", LicenseReportView.as_view(), name="report"),
]
