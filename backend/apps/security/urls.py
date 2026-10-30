from django.urls import path

from apps.security.api import ProjectSecurityView

app_name = "security_api"

urlpatterns = [
    path("projects/<int:project_pk>/security/", ProjectSecurityView.as_view(), name="security"),
]
