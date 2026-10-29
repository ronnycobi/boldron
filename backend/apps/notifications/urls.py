from django.urls import path

from apps.notifications.api import NotificationFeedView, SmsSendView, SmsStatusView

app_name = "notifications"

urlpatterns = [
    path("notifications/", NotificationFeedView.as_view(), name="feed"),
    path("sms/status/", SmsStatusView.as_view(), name="sms-status"),
    path("sms/send/", SmsSendView.as_view(), name="sms-send"),
]
