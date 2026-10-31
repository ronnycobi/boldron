from django.urls import path

from apps.business_rules.api import (
    RuleDetailView,
    RuleEvaluateView,
    RuleImportView,
    RuleListCreateView,
    RuleStatusView,
)

app_name = "business_rules"

urlpatterns = [
    path("projects/<int:project_pk>/rules/",
         RuleListCreateView.as_view(), name="list"),
    path("projects/<int:project_pk>/rules/import/",
         RuleImportView.as_view(), name="import"),
    path("projects/<int:project_pk>/rules/evaluate/",
         RuleEvaluateView.as_view(), name="evaluate"),
    path("rules/<int:pk>/", RuleDetailView.as_view(), name="detail"),
    path("rules/<int:pk>/status/", RuleStatusView.as_view(), name="status"),
]
