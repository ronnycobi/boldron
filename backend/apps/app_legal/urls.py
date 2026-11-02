from django.urls import path

from apps.app_legal.api import AppLegalView, GenerateView, ReviewTriggerView

app_name = "app_legal"

urlpatterns = [
    path("projects/<int:project_pk>/app-legal/", AppLegalView.as_view(), name="overview"),
    path("projects/<int:project_pk>/app-legal/generate/", GenerateView.as_view(), name="generate"),
    path("projects/<int:project_pk>/app-legal/review/", ReviewTriggerView.as_view(), name="review"),
]
