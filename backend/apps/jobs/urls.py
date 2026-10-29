from django.urls import path

from apps.jobs.api import JobDetailView, JobListCreateView

app_name = "jobs_api"

urlpatterns = [
    path("jobs/", JobListCreateView.as_view(), name="list"),
    path("jobs/<int:pk>/", JobDetailView.as_view(), name="detail"),
]
