from django.urls import path

from apps.projects.api import (
    BuildStatusView,
    BuildView,
    EnvVarDetailView,
    EnvVarListCreateView,
    AnalyzeView,
    ProjectAiView,
    ProjectCapabilitiesView,
    ProjectPaymentsView,
    ProjectRepositoryView,
    ProjectDetailView,
    ProjectListCreateView,
)
from apps.workspaces.api import WorkspaceListCreateView

app_name = "projects"

urlpatterns = [
    path("projects/", ProjectListCreateView.as_view(), name="list"),
    path("projects/<int:pk>/", ProjectDetailView.as_view(), name="detail"),
    path("projects/<int:pk>/build-status/", BuildStatusView.as_view(), name="build-status"),
    path("projects/<int:pk>/ai/", ProjectAiView.as_view(), name="ai"),
    path("projects/<int:pk>/repository/", ProjectRepositoryView.as_view(), name="repository"),
    path("projects/<int:pk>/capabilities/", ProjectCapabilitiesView.as_view(), name="capabilities"),
    path("projects/<int:pk>/payments/", ProjectPaymentsView.as_view(), name="payments"),
    path("analyze/", AnalyzeView.as_view(), name="analyze"),
    path("projects/<int:pk>/env/", EnvVarListCreateView.as_view(), name="env-list"),
    path("projects/<int:pk>/env/<int:var_id>/", EnvVarDetailView.as_view(), name="env-detail"),
    path("build/", BuildView.as_view(), name="build"),
    path(
        "projects/<int:project_pk>/workspaces/",
        WorkspaceListCreateView.as_view(),
        name="workspace-list",
    ),
]
