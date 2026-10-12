from django.urls import path

from apps.projects.api import (
    BuildStatusView,
    BuildView,
    ProjectDetailView,
    ProjectListCreateView,
)
from apps.workspaces.api import WorkspaceListCreateView

app_name = "projects"

urlpatterns = [
    path("projects/", ProjectListCreateView.as_view(), name="list"),
    path("projects/<int:pk>/", ProjectDetailView.as_view(), name="detail"),
    path("projects/<int:pk>/build-status/", BuildStatusView.as_view(), name="build-status"),
    path("build/", BuildView.as_view(), name="build"),
    path(
        "projects/<int:project_pk>/workspaces/",
        WorkspaceListCreateView.as_view(),
        name="workspace-list",
    ),
]
