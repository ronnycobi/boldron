from django.urls import path

from apps.incidents.api import (
    IncidentDetailView,
    IncidentListCreateView,
    IncidentNoteView,
    IncidentTransitionView,
)

app_name = "incidents_api"

urlpatterns = [
    path("projects/<int:project_pk>/incidents/", IncidentListCreateView.as_view(), name="list"),
    path("incidents/<int:pk>/", IncidentDetailView.as_view(), name="detail"),
    path("incidents/<int:pk>/transition/", IncidentTransitionView.as_view(), name="transition"),
    path("incidents/<int:pk>/note/", IncidentNoteView.as_view(), name="note"),
]
