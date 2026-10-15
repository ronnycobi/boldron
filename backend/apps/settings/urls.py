from django.urls import path

from apps.settings.api import SettingsOverviewView

app_name = "settings_api"

urlpatterns = [
    path("settings/overview/", SettingsOverviewView.as_view(), name="overview"),
]
