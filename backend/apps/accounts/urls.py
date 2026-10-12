from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.accounts.api import (
    AccountView,
    AvatarView,
    ChangePasswordView,
    LogoutAllView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    TokenObtainView,
    VerifyEmailView,
)
from apps.accounts.views import MeView

app_name = "accounts"

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    # Account management (the signed-in user's own profile/security).
    path("account/", AccountView.as_view(), name="account"),
    path("account/password/", ChangePasswordView.as_view(), name="account-password"),
    path("account/logout-all/", LogoutAllView.as_view(), name="account-logout-all"),
    path("account/avatar/", AvatarView.as_view(), name="account-avatar"),
    # JWT auth for the mobile/API client (the web app uses session login).
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/token/", TokenObtainView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    # Email verification + password reset (shared backend; same tokens as web).
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("auth/resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
