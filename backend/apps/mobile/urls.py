from django.urls import path

from apps.mobile.api import MobileCapabilitiesView, MobilePlanView

app_name = "mobile_api"

urlpatterns = [
    path("mobile/capabilities/", MobileCapabilitiesView.as_view(), name="capabilities"),
    path("mobile/plan/", MobilePlanView.as_view(), name="plan"),
]
