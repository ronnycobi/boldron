from django.urls import path

from apps.data_quality.api import (
    CheckView,
    DataQualityView,
    DatasetCreateView,
    RuleCreateView,
)

app_name = "data_quality"

urlpatterns = [
    path("projects/<int:project_pk>/data-quality/",
         DataQualityView.as_view(), name="overview"),
    path("projects/<int:project_pk>/data-quality/datasets/",
         DatasetCreateView.as_view(), name="datasets"),
    path("data-quality/datasets/<int:pk>/rules/",
         RuleCreateView.as_view(), name="rules"),
    path("data-quality/datasets/<int:pk>/check/", CheckView.as_view(), name="check"),
]
