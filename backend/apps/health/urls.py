from django.urls import path

from apps.health.api import ProjectHealthView

app_name = "health"

urlpatterns = [
    path("projects/<int:project_pk>/health/",
         ProjectHealthView.as_view(), name="score"),
]
