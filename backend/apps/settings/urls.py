from django.urls import path

from apps.settings.api import (
    IntegrationStatusView,
    MarketplaceView,
    MfaConfirmView,
    MfaDisableView,
    MfaEnrollView,
    MfaRecoveryCodesView,
    SecurityView,
    SessionRevokeView,
    SettingsOverviewView,
    SettingsSearchView,
)

app_name = "settings_api"

urlpatterns = [
    path("settings/overview/", SettingsOverviewView.as_view(), name="overview"),
    path("settings/search/", SettingsSearchView.as_view(), name="search"),
    path("settings/integrations/", IntegrationStatusView.as_view(), name="integrations"),
    path("settings/marketplace/", MarketplaceView.as_view(), name="marketplace"),
    path("settings/security/", SecurityView.as_view(), name="security"),
    path("settings/sessions/<int:session_id>/revoke/",
         SessionRevokeView.as_view(), name="session-revoke"),
    path("settings/mfa/enroll/", MfaEnrollView.as_view(), name="mfa-enroll"),
    path("settings/mfa/confirm/", MfaConfirmView.as_view(), name="mfa-confirm"),
    path("settings/mfa/disable/", MfaDisableView.as_view(), name="mfa-disable"),
    path("settings/mfa/recovery-codes/",
         MfaRecoveryCodesView.as_view(), name="mfa-recovery-codes"),
]
