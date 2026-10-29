"""Capability registry honesty + inference from a brief."""
from django.test import SimpleTestCase

from apps.capabilities.infer import infer_capabilities
from apps.capabilities.registry import AVAILABLE, PLANNED, all_capabilities, by_group, get


class RegistryTests(SimpleTestCase):
    def test_every_capability_has_an_honest_status(self):
        for c in all_capabilities():
            self.assertIn(c.status, (AVAILABLE, PLANNED), c.id)

    def test_planned_capabilities_are_not_marked_available(self):
        # The guardrail: things we don't offer yet must be PLANNED.
        for cid in ("subscriptions", "monitoring", "domains", "sms", "analytics"):
            self.assertEqual(get(cid).status, PLANNED, cid)

    def test_real_capabilities_are_available(self):
        for cid in ("auth", "database", "email", "security", "audit", "export",
                    "git", "backups", "files", "payments"):
            self.assertEqual(get(cid).status, AVAILABLE, cid)

    def test_grouped(self):
        groups = dict(by_group())
        self.assertIn("Application", groups)
        self.assertIn("Business", groups)


class InferenceTests(SimpleTestCase):
    def _ids(self, brief):
        return {c.id for c in infer_capabilities(brief)}

    def test_baseline_always_present(self):
        ids = self._ids("something")
        self.assertLessEqual({"users", "auth", "database", "dashboard", "hosting"}, ids)

    def test_crm_brief_infers_crm_and_email(self):
        ids = self._ids("Build a CRM for my construction company with customers, leads and email reminders.")
        self.assertIn("crm", ids)
        self.assertIn("email", ids)

    def test_payments_and_subscriptions_inferred(self):
        ids = self._ids("A SaaS with a monthly subscription and card checkout.")
        self.assertIn("payments", ids)
        self.assertIn("subscriptions", ids)

    def test_uploads_infer_file_storage(self):
        self.assertIn("files", self._ids("Customers upload documents and photos."))


from django.test import TestCase as _TC  # noqa: E402


class RequirementsAnalysisTests(_TC):
    """The AI requirements analysis: brief -> capabilities, honest built/coming."""

    def test_baseline_every_app_gets(self):
        from apps.capabilities.analysis import analyze
        a = analyze("a simple brochure website")
        names = {n for g in a["groups"] for n in [i["name"] for i in g["items"]]}
        self.assertIn("Authentication", names)
        self.assertIn("Database", names)
        self.assertIn("Dashboards", names)

    def test_detects_commerce_and_payments(self):
        from apps.capabilities.analysis import analyze
        a = analyze("an online furniture store with products, cart, checkout and payments")
        ids = {i["id"] for g in a["groups"] for i in g["items"]}
        self.assertIn("ecommerce", ids)
        self.assertIn("payments", ids)

    def test_honest_built_vs_coming_split(self):
        from apps.capabilities.analysis import analyze
        a = analyze("a subscription SaaS with recurring billing and analytics")
        # subscriptions + analytics are planned, not built — never faked.
        subs = next(i for g in a["groups"] for i in g["items"] if i["id"] == "subscriptions")
        self.assertFalse(subs["available"])
        self.assertIn("Subscriptions", a["planned_names"])
        self.assertIn("Analytics", a["planned_names"])
        self.assertEqual(a["total"], a["available_count"] + a["planned_count"])

    def test_summary_from_persisted_ids(self):
        from apps.capabilities.analysis import summary
        s = summary(["auth", "database", "analytics", "not-a-real-id"])
        self.assertEqual(s["total"], 3)  # unknown id dropped
        self.assertEqual(s["available_count"], 2)
        self.assertEqual(s["planned_count"], 1)  # analytics still planned
