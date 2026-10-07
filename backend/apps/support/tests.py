from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Membership, Organization, Role
from apps.support import service
from apps.support.models import SLA_HOURS, SupportTicket, TicketStatus


class SupportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@acme.com", password="x")
        self.org = Organization.objects.create(name="Acme", created_by=self.user)

    def test_create_ticket_opens_and_threads_and_emails(self):
        t = service.create_ticket(organization=self.org, user=self.user,
                                  subject="Can't log in", body="It says password wrong.",
                                  category="bug", priority="high")
        self.assertEqual(t.status, TicketStatus.OPEN)
        self.assertTrue(t.number.startswith("TKT-"))          # brand-neutral, configurable prefix
        self.assertEqual(t.messages.count(), 1)               # first message from the body
        self.assertEqual(len(mail.outbox), 1)                 # confirmation to the customer
        self.assertIn(t.number, mail.outbox[0].subject)

    def test_staff_reply_waits_on_customer_and_emails(self):
        staff = User.objects.create_user(email="agent@example.com", password="x", is_staff=True)
        t = service.create_ticket(organization=self.org, user=self.user, subject="Q", body="hi")
        mail.outbox.clear()
        service.add_message(t, author=staff, body="Try a reset link.", from_staff=True)
        t.refresh_from_db()
        self.assertEqual(t.status, TicketStatus.WAITING)      # now waiting on the customer
        self.assertEqual(len(mail.outbox), 1)                 # customer emailed the reply
        # Customer replies → reopens.
        service.add_message(t, author=self.user, body="Still stuck.", from_staff=False)
        t.refresh_from_db()
        self.assertEqual(t.status, TicketStatus.OPEN)

    def test_internal_note_not_emailed(self):
        staff = User.objects.create_user(email="agent2@example.com", password="x", is_staff=True)
        t = service.create_ticket(organization=self.org, user=self.user, subject="Q", body="hi")
        mail.outbox.clear()
        service.add_message(t, author=staff, body="check their plan", internal=True, from_staff=True)
        self.assertEqual(len(mail.outbox), 0)                 # internal note stays on the desk


class SupportAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@acme.com", password="x")
        self.org = Organization.objects.create(name="Acme", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Role.OWNER)
        self.other = User.objects.create_user(email="stranger@x.com", password="x")
        self.staff = User.objects.create_user(email="agent@example.com", password="x", is_staff=True)

    def test_customer_creates_and_sees_own_ticket_only(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("support:mine"),
                         {"subject": "Help me", "body": "please", "category": "question", "priority": "normal"})
        t = SupportTicket.objects.get()
        # Owner can view it.
        self.assertEqual(self.client.get(reverse("support:ticket", args=[t.id])).status_code, 200)
        # A stranger from another org cannot.
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("support:ticket", args=[t.id])).status_code, 404)

    def test_staff_desk_sees_all_and_can_reply(self):
        t = service.create_ticket(organization=self.org, user=self.owner, subject="Q", body="hi")
        self.client.force_login(self.staff)
        r = self.client.get(reverse("support:desk"))
        self.assertContains(r, t.number)
        self.client.post(reverse("support:desk_ticket", args=[t.id]),
                         {"action": "reply", "body": "On it."})
        t.refresh_from_db()
        self.assertEqual(t.status, "waiting")

    def test_customer_cannot_reach_staff_desk(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("support:desk")).status_code, 403)


class SupportSlaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="c@acme.com", password="x")
        self.org = Organization.objects.create(name="Acme", created_by=self.user)
        self.staff = User.objects.create_user(email="a@example.com", password="x", is_staff=True)

    def _ticket(self, **kw):
        return service.create_ticket(organization=self.org, user=self.user,
                                     subject="Q", body="hi", **kw)

    def test_sla_targets_stamped_from_priority(self):
        t = self._ticket(priority="urgent")
        self.assertIsNotNone(t.first_response_due)
        self.assertIsNotNone(t.resolution_due)
        resp_h, _ = SLA_HOURS["urgent"]
        self.assertAlmostEqual(
            (t.first_response_due - t.created_at).total_seconds(), resp_h * 3600, delta=5)

    def test_first_public_staff_reply_stops_response_clock(self):
        t = self._ticket()
        self.assertIsNone(t.first_responded_at)
        service.add_message(t, author=self.staff, body="hello", from_staff=True)
        t.refresh_from_db()
        self.assertIsNotNone(t.first_responded_at)

    def test_internal_note_does_not_stop_response_clock(self):
        t = self._ticket()
        service.add_message(t, author=self.staff, body="note", internal=True, from_staff=True)
        t.refresh_from_db()
        self.assertIsNone(t.first_responded_at)

    def test_overdue_and_breached_until_answered(self):
        t = self._ticket()
        t.first_response_due = timezone.now() - timedelta(hours=1)  # force past due
        t.save(update_fields=["first_response_due"])
        self.assertTrue(t.response_overdue)
        self.assertEqual(t.sla_state, "breached")
        service.add_message(t, author=self.staff, body="hi", from_staff=True)
        t.refresh_from_db()
        self.assertFalse(t.response_overdue)

    def test_resolving_stamps_time_and_meets_sla(self):
        t = self._ticket()
        service.set_status(t, status="resolved", user=self.staff)
        t.refresh_from_db()
        self.assertIsNotNone(t.resolved_at)
        self.assertEqual(t.sla_state, "met")

    def test_desk_counts_breached(self):
        t = self._ticket()
        t.first_response_due = timezone.now() - timedelta(hours=2)
        t.save(update_fields=["first_response_due"])
        self.client.force_login(self.staff)
        r = self.client.get(reverse("support:desk"))
        self.assertContains(r, "breaching SLA")

    @override_settings(APP_TICKET_PREFIX="HELP")
    def test_ticket_prefix_is_configurable(self):
        self.assertTrue(self._ticket().number.startswith("HELP-"))
