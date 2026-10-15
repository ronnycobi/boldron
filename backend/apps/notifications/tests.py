"""Tests for the email layer (captured via Django's locmem test backend)."""
from django.core import mail
from django.test import TestCase

from apps.notifications.email import send_email, send_invitation_email
from apps.organizations import invitations
from apps.organizations.models import Organization, Role


class SendEmailTests(TestCase):
    def test_send_plain_and_html(self):
        n = send_email(subject="Hi", to="a@x.com", text="hello",
                       html="<p>hello</p>")
        self.assertEqual(n, 1)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["a@x.com"])
        self.assertEqual(msg.subject, "Hi")
        self.assertEqual(msg.alternatives[0][1], "text/html")

    def test_no_recipient_is_noop(self):
        self.assertEqual(send_email(subject="x", to="", text="y"), 0)
        self.assertEqual(len(mail.outbox), 0)


class InvitationEmailTests(TestCase):
    def test_invitation_email_contains_accept_link(self):
        org = Organization.objects.create(name="Acme")
        inv = invitations.create_invitation(org, "new@x.com", role=Role.ADMIN)
        url = "https://example.com/app/invite/TOKEN123/"
        send_invitation_email(inv, url)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["new@x.com"])
        self.assertIn("Acme", msg.subject)
        self.assertIn(url, msg.body)  # plain-text body carries the link


from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402

_User = get_user_model()


def _auth(user):
    from apps.accounts.api import issue_tokens

    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class NotificationPreferenceTests(TestCase):
    def setUp(self):
        self.user = _User.objects.create_user(email="np@x.com", password="pw12345!")

    def test_defaults_to_opt_in(self):
        from apps.notifications.preferences import wants

        self.assertTrue(wants(self.user, "support_updates"))

    def test_unknown_category_always_sends(self):
        from apps.notifications.preferences import wants

        self.assertTrue(wants(self.user, "not_a_category"))

    def test_update_suppresses(self):
        from apps.notifications.preferences import update, wants

        update(self.user, {"support_updates": False})
        self.assertFalse(wants(self.user, "support_updates"))

    def test_api_get_and_patch(self):
        get = self.client.get(reverse("accounts:account-notifications"), **_auth(self.user))
        self.assertEqual(get.status_code, 200)
        self.assertTrue(get.json()["preferences"]["support_updates"])
        patch = self.client.patch(
            reverse("accounts:account-notifications"),
            data={"support_updates": False},
            content_type="application/json", **_auth(self.user),
        )
        self.assertFalse(patch.json()["preferences"]["support_updates"])


class SupportEmailRespectsPreferenceTests(TestCase):
    """The gate genuinely suppresses the optional support emails."""

    def setUp(self):
        from apps.organizations.models import Organization

        self.user = _User.objects.create_user(email="su@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="SupCo")
        self.org.add_member(self.user)

    def test_confirmation_email_suppressed_when_opted_out(self):
        from django.core import mail

        from apps.notifications.preferences import update
        from apps.support.service import create_ticket

        update(self.user, {"support_updates": False})
        mail.outbox = []
        create_ticket(organization=self.org, user=self.user, subject="Help",
                      body="x", category="technical", priority="normal")
        # No confirmation to the user (the support-inbox copy may still send, but
        # that's a different recipient; the user opted out of their own copy).
        to_user = [m for m in mail.outbox if self.user.email in m.to]
        self.assertEqual(to_user, [])

    def test_confirmation_email_sent_by_default(self):
        from django.core import mail
        from apps.support.service import create_ticket

        mail.outbox = []
        create_ticket(organization=self.org, user=self.user, subject="Help",
                      body="x", category="technical", priority="normal")
        to_user = [m for m in mail.outbox if self.user.email in m.to]
        self.assertEqual(len(to_user), 1)
