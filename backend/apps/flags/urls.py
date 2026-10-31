from django.urls import path

from apps.flags.api import (
    FlagDetailView,
    FlagEvaluateView,
    FlagListCreateView,
    FlagToggleView,
)

app_name = "flags"

urlpatterns = [
    path("projects/<int:project_pk>/flags/",
         FlagListCreateView.as_view(), name="list"),
    path("projects/<int:project_pk>/flags/evaluate/",
         FlagEvaluateView.as_view(), name="evaluate"),
    path("flags/<int:pk>/", FlagDetailView.as_view(), name="detail"),
    path("flags/<int:pk>/toggle/", FlagToggleView.as_view(), name="toggle"),
]
