from django.urls import path

from apps.changes.api import (
    ChangeApproveView,
    ChangeDetailView,
    ChangeImplementView,
    ChangeListCreateView,
    ChangeRollbackView,
)

app_name = "changes"

urlpatterns = [
    path("projects/<int:project_pk>/changes/", ChangeListCreateView.as_view(), name="list"),
    path("changes/<int:pk>/", ChangeDetailView.as_view(), name="detail"),
    path("changes/<int:pk>/approve/", ChangeApproveView.as_view(), name="approve"),
    path("changes/<int:pk>/implement/", ChangeImplementView.as_view(), name="implement"),
    path("changes/<int:pk>/rollback/", ChangeRollbackView.as_view(), name="rollback"),
]
