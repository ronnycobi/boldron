"""User model for the platform.

Email is the identity — there is no username. A custom user model is introduced
here, before any other app references it, because swapping AUTH_USER_MODEL later
is extremely costly. Organization membership lives in apps.organizations.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(models.Manager):
    """Manager that creates users keyed by email."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    @staticmethod
    def normalize_email(email):
        # Lowercase the domain part; leave the local part as-is (RFC-safe).
        email = email or ""
        try:
            local, domain = email.strip().rsplit("@", 1)
        except ValueError:
            return email.strip()
        return f"{local}@{domain.lower()}"

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        # Required by Django auth (login, createsuperuser). Look up by email,
        # the USERNAME_FIELD.
        return self.get(**{self.model.USERNAME_FIELD: username})


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)

    # Email ownership: new self-serve sign-ups must confirm their address before
    # full access. Existing accounts are grandfathered verified in the migration,
    # and accepting an invitation (sent to that address) also proves ownership.
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text="Whether the user can log into the Django admin site.",
    )
    date_joined = models.DateTimeField(default=timezone.now)

    # Per-user preferences (declared after date_joined so the field named
    # `timezone` doesn't shadow the imported module above). Blank falls back to
    # the platform default; applied by apps.core.middleware.UserLocaleMiddleware.
    language = models.CharField(max_length=16, blank=True)
    timezone = models.CharField(max_length=64, blank=True)

    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password are already required by USERNAME_FIELD

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def display_name(self):
        """A friendly name for the UI — the full name if set, else the email."""
        return self.full_name.strip() or self.email

    @property
    def avatar_url(self):
        """URL of the uploaded avatar, or '' if none is set."""
        try:
            return self.avatar.url if self.avatar else ""
        except ValueError:
            return ""

    @property
    def initials(self):
        """Up to two uppercase initials for an avatar, from the name or email."""
        name = (self.full_name or "").strip()
        if name:
            parts = name.split()
            if len(parts) >= 2:
                return (parts[0][0] + parts[-1][0]).upper()
            return parts[0][:2].upper()
        return (self.email or "?")[:2].upper()


class LoginEvent(models.Model):
    """A security-relevant account event (spec §13). Append-only history shown in
    the Security Center. `user` may be null for a failed attempt on an unknown
    address; the attempted email is always recorded."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    SESSION_REVOKED = "session_revoked"
    KINDS = [
        (LOGIN_SUCCESS, "Signed in"),
        (LOGIN_FAILED, "Failed sign-in"),
        (LOGOUT, "Signed out"),
        (PASSWORD_CHANGED, "Password changed"),
        (MFA_ENABLED, "MFA enabled"),
        (MFA_DISABLED, "MFA disabled"),
        (SESSION_REVOKED, "Session revoked"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="login_events", null=True, blank=True,
    )
    email = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=24, choices=KINDS)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.email or self.user_id}"


class UserSession(models.Model):
    """Metadata for an active web session (spec §12), keyed to the Django session.
    Lets the Security Center list devices and revoke them. No precise location is
    stored — only what the request headers provide."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_active = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_active"]

    def __str__(self):
        return f"session {self.session_key[:8]}… for {self.user_id}"


class TotpDevice(models.Model):
    """A user's TOTP second factor (spec §10). The shared secret is created at
    enrolment; MFA counts as *enabled* only once `confirmed_at` is set (the user
    proved they can generate a valid code). One device per user — re-enrolling
    replaces it."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device"
    )
    # Base32 secret (RFC 4648). Generated per-user by pyotp; never hard-coded.
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        state = "confirmed" if self.confirmed_at else "pending"
        return f"TOTP ({state}) for {self.user_id}"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class RecoveryCode(models.Model):
    """Single-use backup codes (spec §10). Only a hash is stored — the plaintext
    is shown to the user exactly once, at generation time, and is never
    recoverable afterwards."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"recovery code for {self.user_id} ({'used' if self.used_at else 'unused'})"
