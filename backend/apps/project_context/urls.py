from django.urls import path

from apps.project_context.api import (
    ApplicationGraphView,
    ContextDetailView,
    ContextDigestView,
    ContextListCreateView,
    ProjectIntelligenceView,
)

app_name = "project_context"

urlpatterns = [
    path(
        "projects/<int:project_pk>/context/",
        ContextListCreateView.as_view(),
        name="list",
    ),
    path(
        "projects/<int:project_pk>/context/digest/",
        ContextDigestView.as_view(),
        name="digest",
    ),
    path(
        "projects/<int:project_pk>/intelligence/",
        ProjectIntelligenceView.as_view(),
        name="intelligence",
    ),
    path(
        "projects/<int:project_pk>/graph/",
        ApplicationGraphView.as_view(),
        name="graph",
    ),
    path("context/<int:pk>/", ContextDetailView.as_view(), name="detail"),
]
