"""Mobile / API authentication endpoints (JWT).

The Flutter client signs in here to obtain a short-lived access token and a
rotating refresh token; the web app keeps using session login unchanged. These
endpoints reuse the same brute-force throttling as the web login, so account
protection is identical across every interface. No vendor or framework detail is
exposed — only the tokens and a minimal user payload.
"""
from __future__ import annotations

from django.conf import settings
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


def issue_tokens(user) -> dict:
    """The standard signed-in payload: a fresh token pair plus the user, so a
    client can store the tokens and render the authenticated UI in one step."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


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
        from apps.accounts import security as sec
        from apps.accounts.models import LoginEvent, User

        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            # Bad credentials (AuthenticationFailed) or a malformed request both
            # count as a failed attempt; re-raise so DRF renders the clean 4xx.
            throttle.login_record_failure(email, ip)
            sec.record_failed(email, request)
            raise
        if response.status_code == status.HTTP_200_OK:
            throttle.login_reset(email, ip)
            user = User.objects.filter(email__iexact=email).first()
            if user:  # mobile login has no Django session, so just the event
                sec.record_event(user, request, LoginEvent.LOGIN_SUCCESS)
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


class RegisterView(APIView):
    """Self-serve sign-up. Validates with the same RegistrationForm + password
    policy as the web, runs the shared onboarding (org + owner + free credits +
    verification email), and returns a token pair so the app is signed in at
    once. The account starts unverified, exactly like the web flow."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from apps.accounts.forms import RegistrationForm
        from apps.accounts.registration import onboard_user

        ip = throttle.client_ip(request)
        retry = throttle.SIGNUP_IP.retry_after(ip)
        if retry:
            return Response(
                {"detail": throttle.too_many_message(retry)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        throttle.SIGNUP_IP.hit(ip)

        form = RegistrationForm(data=request.data)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        user = form.save()
        onboard_user(user, org_name=form.cleaned_data.get("org_name", ""), request=request)
        return Response(issue_tokens(user), status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """Confirm an email address from the signed token in the verification link
    (the mobile app captures it from the deep link and posts it here)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from apps.accounts import verification

        token = (request.data.get("token") or "").strip()
        if not token:
            return Response(
                {"detail": "A verification token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user, reason = verification.verify(token)
        if user is None:
            msg = (
                "This verification link has expired — request a new one."
                if reason == "expired"
                else "This verification link is invalid."
            )
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        verification.mark_verified(user)
        return Response({"detail": "Your email address is verified."})


class ResendVerificationView(APIView):
    """Re-send the verification email to the signed-in user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.accounts import verification

        if request.user.email_verified:
            return Response({"detail": "Your email is already verified."})
        verification.send_verification(request, request.user)
        return Response({"detail": "Verification email sent — check your inbox."})


class PasswordResetRequestView(APIView):
    """Start a password reset. Sends the same branded, single-use reset email as
    the web flow. Always returns the same response, so it never reveals whether
    an address has an account (no enumeration)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.contrib.auth.forms import PasswordResetForm
        from django.contrib.auth.tokens import default_token_generator

        email = (request.data.get("email") or "").strip().lower()
        ip = throttle.client_ip(request)
        retry = throttle.reset_retry_after(email, ip)
        if retry:
            return Response(
                {"detail": throttle.too_many_message(retry)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        throttle.reset_record(email, ip)

        form = PasswordResetForm({"email": email})
        if form.is_valid():
            form.save(
                use_https=request.is_secure(),
                token_generator=default_token_generator,
                email_template_name="dashboard/password_reset_email.txt",
                subject_template_name="dashboard/password_reset_subject.txt",
                html_email_template_name="dashboard/password_reset_email.html",
                extra_email_context={"app_name": settings.APP_NAME},
                request=request,
            )
        return Response(
            {"detail": "If that email has an account, a reset link is on its way."}
        )


class PasswordResetConfirmView(APIView):
    """Complete a password reset from the uid + token in the emailed link (the
    same token the web page uses) and a new password."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.contrib.auth.forms import SetPasswordForm
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode

        from apps.accounts.models import User

        uidb64 = (request.data.get("uid") or "").strip()
        token = (request.data.get("token") or "").strip()
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "This reset link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        form = SetPasswordForm(user, data=request.data)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        form.save()
        return Response({"detail": "Your password has been reset — you can sign in now."})


def revoke_all_tokens(user) -> int:
    """Blacklist every outstanding refresh token for the user, so no existing
    device can mint new access tokens. Returns how many were newly revoked.
    (Access tokens are short-lived and expire on their own.)"""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        revoked += int(created)
    return revoked


class AccountView(APIView):
    """The signed-in user's own account: read the full profile, or edit the
    fields they're allowed to change (name, email, language, timezone)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        from apps.accounts.serializers import AccountUpdateSerializer

        ser = AccountUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Change the password (old + new). On success, other devices are signed out
    (their refresh tokens are revoked) and the caller gets a fresh token pair so
    it stays signed in."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.contrib.auth.forms import PasswordChangeForm

        form = PasswordChangeForm(
            request.user,
            data={
                "old_password": request.data.get("old_password", ""),
                "new_password1": request.data.get("new_password1", ""),
                "new_password2": request.data.get("new_password2", ""),
            },
        )
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        form.save()
        revoke_all_tokens(request.user)
        from apps.accounts import security as sec
        from apps.accounts.models import LoginEvent
        sec.record_event(request.user, request, LoginEvent.PASSWORD_CHANGED)
        return Response(issue_tokens(request.user))


class LogoutAllView(APIView):
    """Sign out of every session on every device (revoke all refresh tokens),
    then hand the caller a fresh pair so this device stays signed in."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoked = revoke_all_tokens(request.user)
        return Response({"revoked": revoked, **issue_tokens(request.user)})


class AvatarView(APIView):
    """Upload (POST, multipart ``avatar``) or remove (DELETE) the profile photo."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.accounts.avatars import AvatarError, save_avatar

        try:
            save_avatar(request.user, request.FILES.get("avatar"))
        except AvatarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserSerializer(request.user).data)

    def delete(self, request):
        if request.user.avatar:
            request.user.avatar.delete(save=True)
        return Response(UserSerializer(request.user).data)
