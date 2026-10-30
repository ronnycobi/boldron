from django.urls import path

from apps.testing.api import (
    ProjectCompatibilityView,
    ProjectTestsView,
    TestRunFixView,
)

app_name = "testing_api"

urlpatterns = [
    path("projects/<int:project_pk>/tests/", ProjectTestsView.as_view(), name="tests"),
    path("projects/<int:project_pk>/tests/<int:pk>/fix/", TestRunFixView.as_view(), name="test-fix"),
    path("projects/<int:project_pk>/compatibility/", ProjectCompatibilityView.as_view(), name="compatibility"),
]
