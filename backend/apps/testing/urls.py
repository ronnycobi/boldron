from django.urls import path

from apps.testing.api import ProjectTestsView

app_name = "testing_api"

urlpatterns = [
    path("projects/<int:project_pk>/tests/", ProjectTestsView.as_view(), name="tests"),
]
