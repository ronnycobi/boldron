from django.urls import path

from apps.notifications.api import NotificationFeedView

app_name = "notifications"

urlpatterns = [
    path("notifications/", NotificationFeedView.as_view(), name="feed"),
]
