"""Mobile / API authentication endpoints (JWT).

The Flutter client signs in here to obtain a short-lived access token and a
rotating refresh token; the web app keeps using session login unchanged. These
endpoints reuse the same brute-force throttling as the web login, so account
protection is identical across every interface. No vendor or framework detail is
exposed — only the tokens and a minimal user payload.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.serializers import UserSerializer
from apps.core import throttle


class MobileTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue access + refresh and embed the signed-in user, so the app can render
    the authenticated UI immediately without a second round-trip to ``me/``."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class TokenObtainView(TokenObtainPairView):
    """Email + password -> {access, refresh, user}. Brute-force throttled."""

    serializer_class = MobileTokenObtainPairSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # obtaining a token must not itself require auth

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        ip = throttle.client_ip(request)
        locked = throttle.login_retry_after(email, ip)
        if locked:
            return Response(
                {"detail": throttle.too_many_message(locked)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            # Bad credentials (AuthenticationFailed) or a malformed request both
            # count as a failed attempt; re-raise so DRF renders the clean 4xx.
            throttle.login_record_failure(email, ip)
            raise
        if response.status_code == status.HTTP_200_OK:
            throttle.login_reset(email, ip)
        return response


class LogoutView(APIView):
    """Revoke a refresh token by blacklisting it, so it can no longer be used to
    mint new access tokens. The access token remains valid until it expires (it is
    short-lived); the client discards it on logout."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response(
                {"detail": "A refresh token is required to log out."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            return Response(
                {"detail": "That token is invalid or already revoked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)
