"""Email-verification tokens.

Stateless, signed tokens (no DB row needed): the token carries the user id + the
email it was issued for, signed with SECRET_KEY. It expires, is single-purpose
(its own salt), and is bound to the address — if the user later changes their
email, an old token no longer verifies the new one.
"""
from __future__ import annotations

from django.core import signing

SALT = "accounts.email-verify"
MAX_AGE = 60 * 60 * 72  # 3 days


def make_token(user) -> str:
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=SALT)


def verify(token: str):
    """Return (user, None) on success, or (None, reason) where reason is
    'expired' or 'invalid'."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        return None, "expired"
    except signing.BadSignature:
        return None, "invalid"

    from apps.accounts.models import User

    user = User.objects.filter(pk=data.get("uid")).first()
    if not user or user.email != data.get("email"):
        return None, "invalid"
    return user, None


def mark_verified(user) -> None:
    if not user.email_verified:
        from django.utils import timezone

        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified", "email_verified_at"])


def send_verification(request, user) -> None:
    """Build the absolute verify link for this user and email it (best-effort)."""
    from django.urls import reverse

    from apps.notifications.email import send_verification_email

    link = request.build_absolute_uri(
        reverse("dashboard:verify_email", args=[make_token(user)])
    )
    try:
        send_verification_email(user, link)
    except Exception:
        pass
