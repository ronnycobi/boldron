from django.urls import path

from apps.backups.api import BackupListCreateView, BackupRestoreView

app_name = "backups"

urlpatterns = [
    path("projects/<int:project_pk>/backups/", BackupListCreateView.as_view(), name="list"),
    path("backups/<int:pk>/restore/", BackupRestoreView.as_view(), name="restore"),
]
