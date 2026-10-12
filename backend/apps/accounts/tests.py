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
