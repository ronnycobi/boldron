"""Email delivery — a thin, honest layer over Django's email framework.

send_email() dispatches through whatever EMAIL_BACKEND is configured: real SMTP
in production (set via env), the console backend in dev (prints, never fakes), and
locmem under tests (captured in mail.outbox). Bodies are plain text with an
optional HTML alternative. This is the single place other apps send mail from, so
branding and delivery policy live in one spot.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_email(*, subject: str, to, text: str, html: str | None = None,
               from_email: str | None = None) -> int:
    """Send one email. `to` may be a string or a list. Returns messages sent (0/1)."""
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r for r in recipients if r]
    if not recipients:
        return 0
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    if html:
        msg.attach_alternative(html, "text/html")
    return msg.send(fail_silently=False)


def send_invitation_email(invitation, accept_url: str) -> int:
    """Email an organization invitation with its accept link."""
    org = invitation.organization.name
    brand = settings.APP_NAME
    subject = f"You're invited to {org} on {brand}"
    text = (
        f"You've been invited to join {org} on {brand} as "
        f"{invitation.get_role_display()}.\n\n"
        f"Accept your invitation:\n{accept_url}\n\n"
        f"This link expires on {invitation.expires_at:%B %d, %Y}. "
        "If you weren't expecting this, you can ignore this email."
    )
    html = (
        f"<p>You've been invited to join <strong>{org}</strong> on {brand} as "
        f"{invitation.get_role_display()}.</p>"
        f'<p><a href="{accept_url}">Accept your invitation</a></p>'
        f"<p style=\"color:#667\">This link expires on "
        f"{invitation.expires_at:%B %d, %Y}. If you weren't expecting this, ignore "
        "this email.</p>"
    )
    return send_email(subject=subject, to=invitation.email, text=text, html=html)


def send_verification_email(user, verify_url: str) -> int:
    """Email a new user a link to confirm they own their address."""
    brand = settings.APP_NAME
    subject = f"Confirm your email for {brand}"
    text = (
        f"Welcome to {brand}! Confirm this email address to unlock your account:\n\n"
        f"{verify_url}\n\n"
        "The link expires in a few days. If you didn't create this account, you "
        "can safely ignore this email."
    )
    html = (
        f"<p>Welcome to <strong>{brand}</strong>! Confirm this email address to "
        "unlock your account.</p>"
        f'<p><a href="{verify_url}" style="display:inline-block;background:#4f7cff;'
        'color:#fff;text-decoration:none;font-weight:700;padding:11px 18px;'
        'border-radius:10px">Verify my email</a></p>'
        "<p style=\"color:#667\">The link expires in a few days. If you didn't "
        "create this account, you can safely ignore this email.</p>"
    )
    return send_email(subject=subject, to=user.email, text=text, html=html)
