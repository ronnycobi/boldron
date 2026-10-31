from django.urls import path

from apps.automations.api import (
    AutomationDetailView,
    AutomationListCreateView,
    AutomationRunView,
    AutomationStatusView,
)

app_name = "automations"

urlpatterns = [
    path("projects/<int:project_pk>/automations/",
         AutomationListCreateView.as_view(), name="list"),
    path("automations/<int:pk>/", AutomationDetailView.as_view(), name="detail"),
    path("automations/<int:pk>/status/", AutomationStatusView.as_view(), name="status"),
    path("automations/<int:pk>/run/", AutomationRunView.as_view(), name="run"),
]
