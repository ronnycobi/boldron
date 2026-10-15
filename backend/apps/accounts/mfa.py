"""Multi-factor authentication (TOTP) — real RFC 6238 verification.

This is a genuine second factor: secrets are generated per user with pyotp,
codes are verified cryptographically (with a ±1 step window for clock drift),
and single-use recovery codes are stored only as hashes. Nothing here is faked —
MFA is reported as *enabled* only once the user has proven they can produce a
valid code (`TotpDevice.confirmed_at`).

The short-lived challenge token used between the password step and the code step
is signed (Django signing, 5-minute TTL) so it can't be forged or replayed past
expiry. Secrets are never logged or returned once a device is confirmed.
"""
from __future__ import annotations

import secrets as _secrets

import pyotp
import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.utils import timezone

from apps.accounts.models import LoginEvent, RecoveryCode, TotpDevice

# Namespaces/TTL for the inter-step challenge token (JWT login).
_CHALLENGE_SALT = "accounts.mfa.challenge"
_CHALLENGE_MAX_AGE = 300  # seconds

RECOVERY_CODE_COUNT = 10


# --- state -------------------------------------------------------------------

def is_enabled(user) -> bool:
    """True only when the user has a *confirmed* TOTP device."""
    device = _device(user)
    return bool(device and device.is_confirmed)


def _device(user):
    return TotpDevice.objects.filter(user=user).first()


def _issuer() -> str:
    return getattr(settings, "APP_NAME", None) or "Boldron"


# --- enrolment ---------------------------------------------------------------

def begin_enrollment(user) -> dict:
    """Create (or replace) an unconfirmed device and return what the enrolment
    screen needs: the secret (for manual entry), the otpauth:// URI, and a
    ready-to-render QR as inline SVG. Re-enrolling discards any previous device."""
    TotpDevice.objects.filter(user=user).delete()
    secret = pyotp.random_base32()
    TotpDevice.objects.create(user=user, secret=secret)
    uri = provisioning_uri(user, secret)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg(uri)}


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=_issuer()
    )


def qr_svg(uri: str) -> str:
    """Render an otpauth URI as an inline SVG string (no raster image deps)."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    return img.to_string(encoding="unicode")


def confirm_enrollment(user, code: str) -> list[str] | None:
    """Confirm a pending enrolment by verifying a live code. On success the device
    becomes confirmed (MFA enabled) and a fresh set of recovery codes is generated
    and returned in plaintext ONCE. Returns None if the code is wrong or there is
    no pending device."""
    device = _device(user)
    if device is None or device.is_confirmed:
        return None
    if not pyotp.TOTP(device.secret).verify(_clean(code), valid_window=1):
        return None
    device.confirmed_at = timezone.now()
    device.save(update_fields=["confirmed_at"])
    codes = generate_recovery_codes(user)
    LoginEvent.objects.create(
        user=user, email=user.email, kind=LoginEvent.MFA_ENABLED
    )
    return codes


def disable(user) -> bool:
    """Turn MFA off: remove the device and all recovery codes. Callers must
    re-authenticate the user first (high-risk action)."""
    if not TotpDevice.objects.filter(user=user).exists():
        return False
    TotpDevice.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()
    LoginEvent.objects.create(
        user=user, email=user.email, kind=LoginEvent.MFA_DISABLED
    )
    return True


# --- verification ------------------------------------------------------------

def verify_totp(user, code: str) -> bool:
    device = _device(user)
    if device is None or not device.is_confirmed:
        return False
    return pyotp.TOTP(device.secret).verify(_clean(code), valid_window=1)


def verify_recovery_code(user, code: str) -> bool:
    """Consume a single-use recovery code if it matches an unused one."""
    candidate = _clean(code)
    for rc in RecoveryCode.objects.filter(user=user, used_at__isnull=True):
        if check_password(candidate, rc.code_hash):
            rc.used_at = timezone.now()
            rc.save(update_fields=["used_at"])
            return True
    return False


def verify_any(user, code: str) -> bool:
    """Accept either a current TOTP code or an unused recovery code."""
    return verify_totp(user, code) or verify_recovery_code(user, code)


# --- recovery codes ----------------------------------------------------------

def generate_recovery_codes(user) -> list[str]:
    """Replace the user's recovery codes with a fresh set; return the plaintext
    (shown once). Format: 10 groups of base32 like `abcde-fghij`."""
    RecoveryCode.objects.filter(user=user).delete()
    codes = [_new_code() for _ in range(RECOVERY_CODE_COUNT)]
    # Hash the normalised form so a code entered with or without its dash/spaces
    # still matches on verification.
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=user, code_hash=make_password(_clean(c))) for c in codes]
    )
    return codes


def unused_recovery_code_count(user) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


# --- challenge token (JWT two-step login) ------------------------------------

def issue_challenge(user) -> str:
    """A signed, short-lived token that stands in for 'password verified, second
    factor still required'. Carries only the user id."""
    return signing.dumps({"uid": user.pk}, salt=_CHALLENGE_SALT)


def resolve_challenge(token: str):
    """Return the user for a valid, unexpired challenge token, else None."""
    from apps.accounts.models import User

    try:
        data = signing.loads(token, salt=_CHALLENGE_SALT, max_age=_CHALLENGE_MAX_AGE)
    except signing.BadSignature:
        return None
    return User.objects.filter(pk=data.get("uid")).first()


# --- helpers -----------------------------------------------------------------

def _clean(code: str) -> str:
    return (code or "").strip().replace(" ", "").replace("-", "").lower()


def _new_code() -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    raw = "".join(_secrets.choice(alphabet) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"
