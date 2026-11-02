"""Trust Center (spec §26, §28, §29): a factual subprocessor register, an HONEST
security overview that claims no certifications, and private vulnerability
reports that are never published."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.trust import service
from apps.trust.models import Subprocessor, VulnerabilityReport

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class SubprocessorTests(TestCase):
    def test_register_and_active_list_excludes_removed(self):
        service.register_subprocessor(name="Stripe", category="payment")
        removed = service.register_subprocessor(name="OldVendor", status="removed")
        names = [s.name for s in service.active_subprocessors()]
        self.assertIn("Stripe", names)
        self.assertNotIn("OldVendor", names)

    def test_name_required(self):
        with self.assertRaises(service.TrustError):
            service.register_subprocessor(name="")

    def test_public_register_api(self):
        service.register_subprocessor(name="Anthropic", category="ai")
        resp = self.client.get(reverse("trust:subprocessors"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["subprocessors"][0]["name"], "Anthropic")


class SecurityOverviewTests(TestCase):
    def test_overview_claims_no_certifications(self):
        ov = service.security_overview()
        self.assertEqual(ov["certifications"], [])
        self.assertTrue(ov["controls"])
        # honesty: no false certification words in the control descriptions
        blob = str(ov["controls"]).lower()
        for false_claim in ("soc 2", "iso 27001", "pci dss", "certified"):
            self.assertNotIn(false_claim, blob)

    def test_overview_is_public(self):
        self.assertEqual(self.client.get(reverse("trust:security")).status_code, 200)


class DisclosureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@x.com", password="pw12345!")
        self.staff = User.objects.create_user(email="s@x.com", password="pw12345!", is_staff=True)

    def test_anyone_can_submit_a_report(self):
        resp = self.client.post(reverse("trust:disclosure"),
                                {"summary": "XSS in search", "severity_estimate": "high"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(VulnerabilityReport.objects.count(), 1)

    def test_summary_required(self):
        resp = self.client.post(reverse("trust:disclosure"), {"summary": ""},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_reports_are_staff_only_never_public(self):
        service.submit_vulnerability(summary="secret bug")
        self.assertEqual(
            self.client.get(reverse("trust:reports"), **auth(self.user)).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("trust:reports"), **auth(self.staff)).status_code, 200)

    def test_staff_can_triage(self):
        r = service.submit_vulnerability(summary="bug")
        resp = self.client.post(reverse("trust:report_action", args=[r.id]),
                                {"status": "confirmed"}, content_type="application/json",
                                **auth(self.staff))
        self.assertEqual(resp.json()["status"], "confirmed")


class TrustWebTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="st@x.com", password="pw12345!", is_staff=True)

    def test_public_trust_page_renders_and_takes_disclosure(self):
        html = self.client.get(reverse("dashboard:trust_center")).content.decode()
        self.assertIn("Trust", html)
        self.assertIn("Subprocessors", html)
        # honest: the page explicitly disclaims certification rather than claiming it
        self.assertIn("not a claim of any formal certification", html)
        self.client.post(reverse("dashboard:trust_center"),
                         {"action": "disclose", "summary": "A bug"})
        self.assertEqual(VulnerabilityReport.objects.count(), 1)

    def test_console_trust_is_staff_only_and_adds_subprocessor(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("console:trust"),
                         {"action": "subprocessor", "name": "Brevo", "category": "email"})
        self.assertTrue(Subprocessor.objects.filter(name="Brevo").exists())


class SecurityIncidentTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="si@x.com", password="pw12345!", is_staff=True)

    def test_open_requires_title(self):
        with self.assertRaises(service.TrustError):
            service.open_security_incident(title="")

    def test_notification_cannot_be_sent_before_assessment(self):
        inc = service.open_security_incident(title="Data exposure", severity="high")
        with self.assertRaises(service.TrustError):
            service.mark_notified(inc)   # never auto/premature

    def test_notification_blocked_when_assessed_not_required(self):
        inc = service.open_security_incident(title="Minor issue")
        service.assess_notification(inc, required=False)
        with self.assertRaises(service.TrustError):
            service.mark_notified(inc)

    def test_full_flow_assess_required_then_notify(self):
        from apps.trust.models import SecurityIncident
        inc = service.open_security_incident(title="Breach", severity="critical")
        service.update_security_incident(inc, status="contained")
        service.assess_notification(inc, required=True, note="PII affected")
        service.mark_notified(inc)
        inc.refresh_from_db()
        self.assertTrue(inc.notification_sent)
        self.assertEqual(inc.status, SecurityIncident.Status.CONTAINED)

    def test_console_opens_security_incident(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("console:trust"),
                         {"action": "open_incident", "title": "Suspicious login", "severity": "high"})
        from apps.trust.models import SecurityIncident
        self.assertTrue(SecurityIncident.objects.filter(title="Suspicious login").exists())
