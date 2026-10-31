from django.urls import path

from apps.policies.api import (
    PolicyDetailView,
    PolicyListCreateView,
    PolicyToggleView,
)

app_name = "policies"

urlpatterns = [
    path("projects/<int:project_pk>/policies/",
         PolicyListCreateView.as_view(), name="list"),
    path("policies/<int:pk>/", PolicyDetailView.as_view(), name="detail"),
    path("policies/<int:pk>/toggle/", PolicyToggleView.as_view(), name="toggle"),
]
