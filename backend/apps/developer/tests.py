from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Organization, Role

User = get_user_model()


def auth(user):
    from apps.accounts.api import issue_tokens

    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class ApiKeyModelTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Keys")
        self.user = User.objects.create_user(email="k@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_generate_returns_plaintext_and_stores_only_hash(self):
        from apps.developer.models import ApiKey

        key, plaintext = ApiKey.generate(self.org, "CI", created_by=self.user)
        self.assertTrue(plaintext.startswith("bk_"))
        self.assertNotIn(plaintext.split("_")[-1], key.secret_hash)  # raw secret not stored
        self.assertEqual(ApiKey.resolve(plaintext), key)

    def test_resolve_rejects_tampered_or_revoked(self):
        from django.utils import timezone

        from apps.developer.models import ApiKey

        key, plaintext = ApiKey.generate(self.org, "CI", created_by=self.user)
        self.assertIsNone(ApiKey.resolve(plaintext + "x"))
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        self.assertIsNone(ApiKey.resolve(plaintext))


class ApiKeyAuthTests(TestCase):
    """The key must actually authenticate a real API request."""

    def setUp(self):
        self.org = Organization.objects.create(name="AuthCo")
        self.user = User.objects.create_user(email="auth@x.com", password="pw12345!")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_key_authenticates_the_api(self):
        from apps.developer.models import ApiKey

        _, plaintext = ApiKey.generate(self.org, "CI", created_by=self.user)
        resp = self.client.get(reverse("accounts:me"), HTTP_AUTHORIZATION=f"Api-Key {plaintext}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "auth@x.com")

    def test_bad_key_is_401(self):
        resp = self.client.get(reverse("accounts:me"), HTTP_AUTHORIZATION="Api-Key bk_dead_beef")
        self.assertEqual(resp.status_code, 401)

    def test_x_api_key_header_also_works(self):
        from apps.developer.models import ApiKey

        _, plaintext = ApiKey.generate(self.org, "CI", created_by=self.user)
        resp = self.client.get(reverse("accounts:me"), HTTP_X_API_KEY=plaintext)
        self.assertEqual(resp.status_code, 200)


class ApiKeyApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Co")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_create_returns_plaintext_once(self):
        resp = self.client.post(
            reverse("developer:api-keys", args=[self.org.id]),
            data={"name": "CI"}, content_type="application/json", **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["key"].startswith("bk_"))
        # Listing never returns the plaintext again.
        listed = self.client.get(
            reverse("developer:api-keys", args=[self.org.id]), **auth(self.owner)
        ).json()
        self.assertNotIn("key", listed[0])
        self.assertTrue(listed[0]["masked"].startswith("bk_"))

    def test_member_cannot_create(self):
        resp = self.client.post(
            reverse("developer:api-keys", args=[self.org.id]),
            data={"name": "x"}, content_type="application/json", **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_revoke(self):
        from apps.developer.models import ApiKey

        key, _ = ApiKey.generate(self.org, "CI", created_by=self.owner)
        resp = self.client.post(
            reverse("developer:api-key-revoke", args=[self.org.id, key.id]),
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 200)
        key.refresh_from_db()
        self.assertFalse(key.is_active)


class WebhookApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="wo@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="wm@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Hooks")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_create_requires_https_and_known_events(self):
        bad = self.client.post(
            reverse("developer:webhooks", args=[self.org.id]),
            data={"url": "http://insecure.example", "events": ["build.completed"]},
            content_type="application/json", **auth(self.owner),
        )
        self.assertEqual(bad.status_code, 400)
        unknown = self.client.post(
            reverse("developer:webhooks", args=[self.org.id]),
            data={"url": "https://ok.example/hook", "events": ["not.a.real.event"]},
            content_type="application/json", **auth(self.owner),
        )
        self.assertEqual(unknown.status_code, 400)

    def test_create_returns_secret_once(self):
        resp = self.client.post(
            reverse("developer:webhooks", args=[self.org.id]),
            data={"url": "https://ok.example/hook", "events": ["build.completed"]},
            content_type="application/json", **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("secret", resp.json())

    def test_member_cannot_create(self):
        resp = self.client.post(
            reverse("developer:webhooks", args=[self.org.id]),
            data={"url": "https://ok.example/hook"},
            content_type="application/json", **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)


class WebhookDeliveryTests(TestCase):
    """Delivery signs the payload and records every attempt honestly."""

    def setUp(self):
        self.org = Organization.objects.create(name="Deliver")

    def _webhook(self, events=None):
        from apps.developer.models import Webhook

        return Webhook.objects.create(
            organization=self.org, url="https://ok.example/hook",
            events=events if events is not None else ["build.completed"],
            secret="s3cr3t",
        )

    @override_settings(WEBHOOKS_ALLOW_IN_TESTS=True)
    def test_dispatch_signs_and_records_success(self):
        from apps.developer import service
        from apps.developer.models import WebhookDelivery

        wh = self._webhook()
        with mock.patch("apps.developer.service._post", return_value=200) as post:
            deliveries = service.dispatch(self.org, "build.completed", {"project_id": 1})
        self.assertEqual(len(deliveries), 1)
        self.assertTrue(deliveries[0].success)
        # The signature header was computed over the exact body.
        _, kwargs = post.call_args.args, post.call_args.kwargs
        args = post.call_args.args
        url, body, headers = args
        self.assertEqual(headers["X-Boldron-Signature"], service.sign("s3cr3t", body))
        self.assertEqual(WebhookDelivery.objects.filter(success=True).count(), 1)

    @override_settings(WEBHOOKS_ALLOW_IN_TESTS=True)
    def test_dispatch_records_failure_without_raising(self):
        from apps.developer import service

        self._webhook()
        with mock.patch("apps.developer.service._post", side_effect=OSError("boom")):
            deliveries = service.dispatch(self.org, "build.completed", {})
        self.assertEqual(len(deliveries), 1)
        self.assertFalse(deliveries[0].success)
        self.assertIn("boom", deliveries[0].error)

    @override_settings(WEBHOOKS_ALLOW_IN_TESTS=True)
    def test_unknown_event_is_not_dispatched(self):
        from apps.developer import service

        self._webhook()
        self.assertEqual(service.dispatch(self.org, "nope.event", {}), [])

    @override_settings(WEBHOOKS_ALLOW_IN_TESTS=True)
    def test_only_subscribed_webhooks_receive(self):
        from apps.developer import service

        self._webhook(events=["build.completed"])
        other_org = Organization.objects.create(name="Other")
        with mock.patch("apps.developer.service._post", return_value=200):
            # An event no webhook subscribes to is still known but matches none here
            # because the only webhook is in self.org, not other_org.
            self.assertEqual(service.dispatch(other_org, "build.completed", {}), [])
