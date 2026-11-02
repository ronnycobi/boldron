from django.urls import path

from apps.consent.api import CookieConsentView, MarketingConsentView

app_name = "consent"

urlpatterns = [
    path("consent/cookies/", CookieConsentView.as_view(), name="cookies"),
    path("consent/marketing/", MarketingConsentView.as_view(), name="marketing"),
]
