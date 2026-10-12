from django.urls import path

from apps.deployments.api import (
    DeploymentApproveView,
    DeploymentDetailView,
    DeploymentListCreateView,
    DeploymentRunView,
    EnvironmentSummaryView,
)

app_name = "deployments"

urlpatterns = [
    path(
        "projects/<int:project_pk>/deployments/",
        DeploymentListCreateView.as_view(),
        name="list",
    ),
    path(
        "projects/<int:project_pk>/environments/",
        EnvironmentSummaryView.as_view(),
        name="environments",
    ),
    path("deployments/<int:pk>/", DeploymentDetailView.as_view(), name="detail"),
    path(
        "deployments/<int:pk>/approve/",
        DeploymentApproveView.as_view(),
        name="approve",
    ),
    path("deployments/<int:pk>/run/", DeploymentRunView.as_view(), name="run"),
]
