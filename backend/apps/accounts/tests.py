from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user_normalizes_email_domain(self):
        user = User.objects.create_user(email="Ada@Example.COM", password="pw12345!")
        self.assertEqual(user.email, "Ada@example.com")
        self.assertTrue(user.check_password("pw12345!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="pw12345!")

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email="root@example.com", password="pw12345!"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_email_is_the_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, [])

    def test_get_by_natural_key_enables_authentication(self):
        from django.contrib.auth import authenticate

        User.objects.create_user(email="log@example.com", password="pw12345!")
        # Exercises ModelBackend -> manager.get_by_natural_key (admin login path).
        self.assertEqual(User.objects.get_by_natural_key("log@example.com").email, "log@example.com")
        self.assertIsNotNone(authenticate(username="log@example.com", password="pw12345!"))
        self.assertIsNone(authenticate(username="log@example.com", password="wrong"))

    def test_short_name(self):
        user = User.objects.create_user(
            email="grace@example.com", password="pw12345!", full_name="Grace Hopper"
        )
        self.assertEqual(user.short_name, "Grace")


class MeEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="dev@example.com", password="pw12345!", full_name="Dev User"
        )

    def test_me_requires_authentication(self):
        # With JWT auth active, an unauthenticated API request answers 401.
        resp = self.client.get(reverse("accounts:me"))
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_user_and_organizations(self):
        from apps.organizations.models import Organization, Role

        org = Organization.objects.create(name="Acme")
        org.add_member(self.user, role=Role.OWNER)

        self.client.force_login(self.user)
        resp = self.client.get(reverse("accounts:me"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["email"], "dev@example.com")
        self.assertEqual(len(body["organizations"]), 1)
        self.assertEqual(body["organizations"][0]["slug"], "acme")
        self.assertEqual(body["organizations"][0]["role"], "owner")


class JwtAuthEndpointTests(TestCase):
    """The mobile/API auth flow: obtain -> use -> refresh -> revoke."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # throttle state is cache-backed; isolate each test
        self.email = "mob@example.com"
        self.password = "pw12345!"
        self.user = User.objects.create_user(
            email=self.email, password=self.password, full_name="Mobile User"
        )

    def _obtain(self):
        return self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": self.email, "password": self.password},
            content_type="application/json",
        )

    def test_obtain_returns_tokens_and_user(self):
        resp = self._obtain()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body["user"]["email"], self.email)
        self.assertIn("avatar_url", body["user"])  # mobile needs the richer payload

    def test_bad_credentials_rejected(self):
        resp = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": self.email, "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_access_token_authenticates_protected_endpoint(self):
        access = self._obtain().json()["access"]
        resp = self.client.get(
            reverse("accounts:me"), HTTP_AUTHORIZATION=f"Bearer {access}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], self.email)

    def test_me_rejects_a_garbage_bearer_token(self):
        resp = self.client.get(
            reverse("accounts:me"), HTTP_AUTHORIZATION="Bearer not-a-real-token"
        )
        self.assertEqual(resp.status_code, 401)

    def test_refresh_issues_a_new_access_token(self):
        refresh = self._obtain().json()["refresh"]
        resp = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": refresh},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())

    def test_logout_blacklists_the_refresh_token(self):
        tokens = self._obtain().json()
        access, refresh = tokens["access"], tokens["refresh"]
        out = self.client.post(
            reverse("accounts:logout"),
            data={"refresh": refresh},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(out.status_code, 205)
        # The revoked refresh token can no longer mint access tokens.
        again = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": refresh},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 401)

    def test_repeated_failures_are_throttled(self):
        from apps.core.throttle import LOGIN_USER

        for _ in range(LOGIN_USER.limit):
            self.client.post(
                reverse("accounts:token-obtain"),
                data={"email": self.email, "password": "wrong"},
                content_type="application/json",
            )
        locked = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": self.email, "password": self.password},
            content_type="application/json",
        )
        self.assertEqual(locked.status_code, 429)


class RegistrationApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _register(self, **over):
        payload = {
            "full_name": "New Person",
            "email": "new@example.com",
            "org_name": "New Co",
            "password1": "sup3r-s3cret-pw",
            "password2": "sup3r-s3cret-pw",
        }
        payload.update(over)
        return self.client.post(
            reverse("accounts:register"), data=payload, content_type="application/json"
        )

    def test_register_creates_user_org_and_returns_tokens(self):
        from apps.credits.services import get_account
        from apps.organizations.models import Organization

        resp = self._register()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body["user"]["email"], "new@example.com")
        self.assertFalse(body["user"]["email_verified"])  # starts unverified
        # Onboarding ran: the org exists, the user owns it, with a free account.
        self.assertEqual(len(body["user"]["organizations"]), 1)
        org = Organization.objects.get(name="New Co")
        self.assertEqual(org.memberships.first().role, "owner")
        self.assertIsNotNone(get_account(org))

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="new@example.com", password="x")
        resp = self._register()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json())

    def test_register_rejects_password_mismatch(self):
        resp = self._register(password2="different-pw-entirely")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password2", resp.json())

    def test_issued_token_authenticates(self):
        access = self._register().json()["access"]
        me = self.client.get(reverse("accounts:me"), HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "new@example.com")


class EmailVerificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="verify@example.com", password="pw12345!")

    def test_valid_token_verifies(self):
        from apps.accounts import verification

        token = verification.make_token(self.user)
        resp = self.client.post(
            reverse("accounts:verify-email"),
            data={"token": token},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_invalid_token_rejected(self):
        resp = self.client.post(
            reverse("accounts:verify-email"),
            data={"token": "garbage"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_resend_requires_auth(self):
        resp = self.client.post(reverse("accounts:resend-verification"))
        self.assertEqual(resp.status_code, 401)

    def test_resend_for_authenticated_user(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:resend-verification"))
        self.assertEqual(resp.status_code, 200)


class AccountApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = User.objects.create_user(
            email="acct@example.com", password="old-pw-12345!", full_name="Acct User"
        )

    def _auth(self):
        from apps.accounts.api import issue_tokens

        return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(self.user)['access']}"}

    def test_get_account_returns_profile(self):
        resp = self.client.get(reverse("accounts:account"), **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "acct@example.com")

    def test_patch_updates_profile(self):
        resp = self.client.patch(
            reverse("accounts:account"),
            data={"full_name": "Renamed", "language": "fr"},
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Renamed")
        self.assertEqual(self.user.language, "fr")

    def test_patch_rejects_taken_email(self):
        User.objects.create_user(email="taken@example.com", password="x")
        resp = self.client.patch(
            reverse("accounts:account"),
            data={"email": "taken@example.com"},
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_change_password_revokes_old_refresh_and_reissues(self):
        from apps.accounts.api import issue_tokens

        old_refresh = issue_tokens(self.user)["refresh"]
        resp = self.client.post(
            reverse("accounts:account-password"),
            data={
                "old_password": "old-pw-12345!",
                "new_password1": "new-pw-67890!",
                "new_password2": "new-pw-67890!",
            },
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())  # caller stays signed in
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-pw-67890!"))
        again = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": old_refresh},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 401)

    def test_logout_all_revokes_outstanding_tokens(self):
        from apps.accounts.api import issue_tokens

        other = issue_tokens(self.user)["refresh"]
        resp = self.client.post(reverse("accounts:account-logout-all"), **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())
        again = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": other},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 401)

    def test_account_requires_auth(self):
        self.assertEqual(self.client.get(reverse("accounts:account")).status_code, 401)


class PasswordResetApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = User.objects.create_user(email="reset@example.com", password="old-pw-12345!")

    def test_request_is_silent_about_unknown_emails(self):
        # Known and unknown addresses get the same response (no enumeration).
        known = self.client.post(
            reverse("accounts:password-reset"),
            data={"email": "reset@example.com"},
            content_type="application/json",
        )
        unknown = self.client.post(
            reverse("accounts:password-reset"),
            data={"email": "nobody@example.com"},
            content_type="application/json",
        )
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.json(), unknown.json())

    def test_confirm_sets_a_new_password(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        resp = self.client.post(
            reverse("accounts:password-reset-confirm"),
            data={
                "uid": uid,
                "token": token,
                "new_password1": "brand-new-pw-999!",
                "new_password2": "brand-new-pw-999!",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-pw-999!"))

    def test_confirm_rejects_a_bad_token(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self.client.post(
            reverse("accounts:password-reset-confirm"),
            data={
                "uid": uid,
                "token": "bad-token",
                "new_password1": "brand-new-pw-999!",
                "new_password2": "brand-new-pw-999!",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class SecurityServiceTests(TestCase):
    """Login-history + active-session tracking that powers the Security Center."""

    def setUp(self):
        from django.test import RequestFactory

        self.user = User.objects.create_user(email="sec@x.com", password="pw12345!")
        self.rf = RequestFactory()

    def _request(self, ua="Mozilla/5.0 (Macintosh) Chrome/120"):
        req = self.rf.get("/", HTTP_USER_AGENT=ua, REMOTE_ADDR="5.6.7.8")
        return req

    def test_parse_user_agent_is_coarse(self):
        from apps.accounts import security

        self.assertEqual(
            security.parse_user_agent("Mozilla/5.0 (Macintosh) Chrome/120"),
            {"browser": "Chrome", "os": "macOS"},
        )
        self.assertEqual(
            security.parse_user_agent("Dart/3 (dart:io) flutter")["browser"],
            "Mobile app",
        )

    def test_record_login_creates_event_and_session(self):
        from apps.accounts import security
        from apps.accounts.models import LoginEvent, UserSession

        req = self._request()
        req.session = _DummySession("key-1")
        security.record_login(self.user, req)
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.user, kind=LoginEvent.LOGIN_SUCCESS
            ).exists()
        )
        self.assertTrue(
            UserSession.objects.filter(user=self.user, session_key="key-1").exists()
        )

    def test_record_failed_stores_email_without_user(self):
        from apps.accounts import security
        from apps.accounts.models import LoginEvent

        security.record_failed("ghost@x.com", self._request())
        e = LoginEvent.objects.get(kind=LoginEvent.LOGIN_FAILED)
        self.assertIsNone(e.user)
        self.assertEqual(e.email, "ghost@x.com")

    def test_security_status_reports_honest_mfa(self):
        from apps.accounts import security

        status = security.security_status(self.user)
        self.assertTrue(status["password_set"])
        # MFA is now implemented (P1b): available to everyone, off until enrolled.
        self.assertTrue(status["mfa_available"])
        self.assertFalse(status["mfa_enabled"])

    def test_session_dict_never_exposes_raw_key(self):
        from apps.accounts import security
        from apps.accounts.models import UserSession

        s = UserSession.objects.create(
            user=self.user, session_key="secret-key", ip="1.2.3.4"
        )
        d = security.session_dict(s, current_key="secret-key")
        self.assertNotIn("session_key", d)
        self.assertTrue(d["current"])

    def test_revoke_by_id_deletes_session(self):
        from apps.accounts import security
        from apps.accounts.models import UserSession

        s = UserSession.objects.create(user=self.user, session_key="k2", ip="1.1.1.1")
        self.assertTrue(
            security.revoke_session_by_id(self.user, s.id, request=self._request())
        )
        self.assertFalse(UserSession.objects.filter(id=s.id).exists())


class _DummySession:
    def __init__(self, key):
        self.session_key = key


class MfaTests(TestCase):
    """Real TOTP second factor: enrol, confirm, verify, recovery codes, disable,
    and the two-step JWT login it enforces."""

    def setUp(self):
        self.user = User.objects.create_user(email="mfa@x.com", password="pw12345!")

    def _code(self):
        import pyotp

        from apps.accounts.models import TotpDevice

        return pyotp.TOTP(TotpDevice.objects.get(user=self.user).secret).now()

    def test_enrollment_is_not_enabled_until_confirmed(self):
        from apps.accounts import mfa

        enroll = mfa.begin_enrollment(self.user)
        self.assertIn("otpauth://", enroll["otpauth_uri"])
        self.assertIn("<svg", enroll["qr_svg"])
        self.assertFalse(mfa.is_enabled(self.user))  # pending, not confirmed

    def test_confirm_with_valid_code_enables_and_returns_recovery_codes(self):
        from apps.accounts import mfa
        from apps.accounts.models import LoginEvent

        mfa.begin_enrollment(self.user)
        codes = mfa.confirm_enrollment(self.user, self._code())
        self.assertEqual(len(codes), mfa.RECOVERY_CODE_COUNT)
        self.assertTrue(mfa.is_enabled(self.user))
        self.assertTrue(
            LoginEvent.objects.filter(user=self.user, kind=LoginEvent.MFA_ENABLED).exists()
        )

    def test_confirm_with_bad_code_does_not_enable(self):
        from apps.accounts import mfa

        mfa.begin_enrollment(self.user)
        self.assertIsNone(mfa.confirm_enrollment(self.user, "000000"))
        self.assertFalse(mfa.is_enabled(self.user))

    def test_recovery_code_is_single_use(self):
        from apps.accounts import mfa

        mfa.begin_enrollment(self.user)
        codes = mfa.confirm_enrollment(self.user, self._code())
        one = codes[0]
        self.assertTrue(mfa.verify_recovery_code(self.user, one))
        self.assertFalse(mfa.verify_recovery_code(self.user, one))  # already used
        self.assertEqual(mfa.unused_recovery_code_count(self.user), mfa.RECOVERY_CODE_COUNT - 1)

    def test_verify_any_accepts_totp_and_recovery(self):
        from apps.accounts import mfa

        mfa.begin_enrollment(self.user)
        codes = mfa.confirm_enrollment(self.user, self._code())
        self.assertTrue(mfa.verify_any(self.user, self._code()))
        self.assertTrue(mfa.verify_any(self.user, codes[1]))

    def test_disable_removes_device_and_codes(self):
        from apps.accounts import mfa
        from apps.accounts.models import LoginEvent, RecoveryCode, TotpDevice

        mfa.begin_enrollment(self.user)
        mfa.confirm_enrollment(self.user, self._code())
        self.assertTrue(mfa.disable(self.user))
        self.assertFalse(TotpDevice.objects.filter(user=self.user).exists())
        self.assertFalse(RecoveryCode.objects.filter(user=self.user).exists())
        self.assertTrue(
            LoginEvent.objects.filter(user=self.user, kind=LoginEvent.MFA_DISABLED).exists()
        )

    def test_challenge_token_roundtrip_and_expiry(self):
        from apps.accounts import mfa

        token = mfa.issue_challenge(self.user)
        self.assertEqual(mfa.resolve_challenge(token), self.user)
        self.assertIsNone(mfa.resolve_challenge("tampered.token.value"))


class MfaJwtLoginTests(TestCase):
    """The JWT login must stop at a challenge when MFA is on, and only hand over
    tokens after a valid second factor."""

    def setUp(self):
        from apps.accounts import mfa

        self.user = User.objects.create_user(email="jwtmfa@x.com", password="pw12345!")
        mfa.begin_enrollment(self.user)
        import pyotp

        from apps.accounts.models import TotpDevice

        self.secret = TotpDevice.objects.get(user=self.user).secret
        mfa.confirm_enrollment(self.user, pyotp.TOTP(self.secret).now())

    def _totp(self):
        import pyotp

        return pyotp.TOTP(self.secret).now()

    def test_token_endpoint_returns_challenge_not_tokens(self):
        resp = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": "jwtmfa@x.com", "password": "pw12345!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["mfa_required"])
        self.assertIn("mfa_token", body)
        self.assertNotIn("access", body)

    def test_verify_exchanges_code_for_tokens(self):
        challenge = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": "jwtmfa@x.com", "password": "pw12345!"},
            content_type="application/json",
        ).json()["mfa_token"]
        resp = self.client.post(
            reverse("accounts:mfa-verify"),
            data={"mfa_token": challenge, "code": self._totp()},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_verify_rejects_bad_code(self):
        challenge = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": "jwtmfa@x.com", "password": "pw12345!"},
            content_type="application/json",
        ).json()["mfa_token"]
        resp = self.client.post(
            reverse("accounts:mfa-verify"),
            data={"mfa_token": challenge, "code": "000000"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_user_without_mfa_still_gets_tokens_directly(self):
        User.objects.create_user(email="plain@x.com", password="pw12345!")
        resp = self.client.post(
            reverse("accounts:token-obtain"),
            data={"email": "plain@x.com", "password": "pw12345!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())


class ProfileAndPrefsTests(TestCase):
    """P1c: extra profile fields + accessibility preferences (real effects)."""

    def setUp(self):
        self.user = User.objects.create_user(email="p1c@x.com", password="pw12345!")

    def test_font_scale_factor_maps_choices(self):
        self.user.font_scale = User.FONT_LG
        self.assertEqual(self.user.font_scale_factor, 1.15)
        self.user.font_scale = User.FONT_MD
        self.assertEqual(self.user.font_scale_factor, 1.0)

    def test_account_patch_updates_profile_and_prefs(self):
        from apps.accounts.api import issue_tokens

        auth = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(self.user)['access']}"}
        resp = self.client.patch(
            reverse("accounts:account"),
            data={
                "job_title": "Founder",
                "pronouns": "they/them",
                "bio": "Building things.",
                "font_scale": "lg",
                "reduce_motion": True,
            },
            content_type="application/json",
            **auth,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["job_title"], "Founder")
        self.assertEqual(body["pronouns"], "they/them")
        self.assertEqual(body["font_scale"], "lg")
        self.assertTrue(body["reduce_motion"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.job_title, "Founder")
        self.assertTrue(self.user.reduce_motion)

    def test_me_payload_includes_new_fields(self):
        from apps.accounts.api import issue_tokens

        auth = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(self.user)['access']}"}
        body = self.client.get(reverse("accounts:me"), **auth).json()
        for key in ("job_title", "pronouns", "bio", "font_scale", "reduce_motion"):
            self.assertIn(key, body)
