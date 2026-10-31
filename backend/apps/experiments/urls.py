from django.urls import path

from apps.experiments.api import (
    ExperimentAssignView,
    ExperimentConvertView,
    ExperimentDetailView,
    ExperimentListCreateView,
    ExperimentStatusView,
)

app_name = "experiments"

urlpatterns = [
    path("projects/<int:project_pk>/experiments/",
         ExperimentListCreateView.as_view(), name="list"),
    path("experiments/<int:pk>/", ExperimentDetailView.as_view(), name="detail"),
    path("experiments/<int:pk>/status/", ExperimentStatusView.as_view(), name="status"),
    path("experiments/<int:pk>/assign/", ExperimentAssignView.as_view(), name="assign"),
    path("experiments/<int:pk>/convert/", ExperimentConvertView.as_view(), name="convert"),
]
