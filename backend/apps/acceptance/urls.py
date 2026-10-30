from django.urls import path

from apps.acceptance.api import (
    AcceptanceImportView,
    AcceptanceListCreateView,
    AcceptanceVerifyView,
)

app_name = "acceptance"

urlpatterns = [
    path("projects/<int:project_pk>/acceptance/",
         AcceptanceListCreateView.as_view(), name="list"),
    path("projects/<int:project_pk>/acceptance/import/",
         AcceptanceImportView.as_view(), name="import"),
    path("acceptance/<int:pk>/verify/",
         AcceptanceVerifyView.as_view(), name="verify"),
]
