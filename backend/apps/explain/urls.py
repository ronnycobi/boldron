from django.urls import path

from apps.explain.api import ExplainView

app_name = "explain"

urlpatterns = [
    path("projects/<int:project_pk>/explain/", ExplainView.as_view(), name="explain"),
]
