from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.accounts.api import LogoutView, TokenObtainView
from apps.accounts.views import MeView

app_name = "accounts"

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    # JWT auth for the mobile/API client (the web app uses session login).
    path("auth/token/", TokenObtainView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
]
