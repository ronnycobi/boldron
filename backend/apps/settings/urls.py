from django.urls import path

from apps.settings.api import (
    SecurityView,
    SessionRevokeView,
    SettingsOverviewView,
)

app_name = "settings_api"

urlpatterns = [
    path("settings/overview/", SettingsOverviewView.as_view(), name="overview"),
    path("settings/security/", SecurityView.as_view(), name="security"),
    path("settings/sessions/<int:session_id>/revoke/",
         SessionRevokeView.as_view(), name="session-revoke"),
]
