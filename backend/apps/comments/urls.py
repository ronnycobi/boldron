from django.urls import path

from apps.comments.api import ProjectCommentsView

app_name = "comments_api"

urlpatterns = [
    path("projects/<int:project_pk>/comments/", ProjectCommentsView.as_view(), name="list"),
]
