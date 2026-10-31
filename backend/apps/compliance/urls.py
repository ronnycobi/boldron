from django.urls import path

from apps.compliance.api import (
    ComplianceAttestView,
    ComplianceSeedView,
    ComplianceView,
)

app_name = "compliance"

urlpatterns = [
    path("projects/<int:project_pk>/compliance/", ComplianceView.as_view(), name="overview"),
    path("projects/<int:project_pk>/compliance/seed/",
         ComplianceSeedView.as_view(), name="seed"),
    path("compliance/controls/<int:pk>/attest/",
         ComplianceAttestView.as_view(), name="attest"),
]
