from django.urls import path

from apps.performance.api import BudgetView, PerformanceView, SampleView

app_name = "performance"

urlpatterns = [
    path("projects/<int:project_pk>/performance/",
         PerformanceView.as_view(), name="overview"),
    path("projects/<int:project_pk>/performance/samples/",
         SampleView.as_view(), name="samples"),
    path("projects/<int:project_pk>/performance/budgets/",
         BudgetView.as_view(), name="budgets"),
]
