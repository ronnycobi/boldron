from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.credits.services import ensure_account
from apps.organizations.models import Organization, Role

User = get_user_model()


def auth(user):
    from apps.accounts.api import issue_tokens

    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class SettingsServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="u@x.com", password="pw12345!", full_name="Settings User"
        )
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_overview_has_scopes_and_catalog(self):
        from apps.settings import service

        data = service.overview(self.user)
        self.assertIn("account", data["sections"])
        self.assertIn("organization", data["sections"])
        self.assertIn("project", data["sections"])
        # Built sections are marked available; unbuilt ones are honest, not faked.
        account = {s["key"]: s for s in data["sections"]["account"]}
        self.assertTrue(account["profile"]["available"])
        self.assertFalse(account["appearance"]["available"])

    def test_unverified_email_raises_an_alert(self):
        from apps.settings import service

        alerts = service.alerts_for(self.user)
        self.assertTrue(any(a["area"] == "account" for a in alerts))

    def test_verified_email_has_no_account_alert(self):
        from apps.settings import service

        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])
        alerts = service.alerts_for(self.user)
        self.assertFalse(any(a["area"] == "account" for a in alerts))

    def test_low_credits_alert(self):
        from apps.settings import service

        acct = ensure_account(self.org, plan="free")  # 1000
        acct.balance = 50  # < 15%
        acct.save(update_fields=["balance"])
        alerts = service.alerts_for(self.user)
        self.assertTrue(any(a["area"] == "billing" for a in alerts))

    def test_organization_status_reports_role_and_plan(self):
        from apps.settings import service

        ensure_account(self.org, plan="pro")
        orgs = service.organization_status(self.user)
        self.assertEqual(orgs[0]["role"], "owner")
        self.assertTrue(orgs[0]["can_manage"])
        self.assertEqual(orgs[0]["plan"], "pro")

    def test_permissions(self):
        from apps.settings import service

        member = User.objects.create_user(email="m@x.com", password="pw12345!")
        self.org.add_member(member, role=Role.MEMBER)
        self.assertTrue(service.can_view_org_settings(member, self.org))
        self.assertFalse(service.can_manage_org_settings(member, self.org))
        self.assertTrue(service.can_manage_org_settings(self.user, self.org))


class SettingsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="api@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_overview_requires_auth(self):
        resp = self.client.get(reverse("settings_api:overview"))
        self.assertEqual(resp.status_code, 401)

    def test_overview_returns_catalog_without_web_routes(self):
        resp = self.client.get(reverse("settings_api:overview"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("alerts", body)
        self.assertIn("sections", body)
        # Web-only route names must not leak into the API payload.
        for scope in body["sections"].values():
            for s in scope:
                self.assertNotIn("route", s)


class SettingsCenterPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="web@x.com", password="pw12345!", full_name="Web User"
        )
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_center_renders(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("dashboard:settings_center"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Your account")
        self.assertContains(r, "Organization")

    def test_old_preferences_page_still_works(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(r.status_code, 200)
