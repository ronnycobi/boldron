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
        # Appearance & accessibility are wired (P1c); connected accounts are not.
        self.assertTrue(account["appearance"]["available"])
        self.assertTrue(account["accessibility"]["available"])
        self.assertFalse(account["connected"]["available"])
        # Org developer + integrations are wired (P4).
        org = {s["key"]: s for s in data["sections"]["organization"]}
        self.assertTrue(org["developer"]["available"])
        self.assertTrue(org["integrations"]["available"])

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


class SecurityApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sec@x.com", password="pw12345!")

    def test_security_requires_auth(self):
        resp = self.client.get(reverse("settings_api:security"))
        self.assertEqual(resp.status_code, 401)

    def test_security_returns_status_sessions_history(self):
        from apps.accounts import security

        security.record_event(
            self.user, _FakeRequest(), security.LoginEvent.LOGIN_SUCCESS
        )
        resp = self.client.get(reverse("settings_api:security"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("status", body)
        self.assertFalse(body["status"]["mfa_enabled"])
        self.assertTrue(body["status"]["mfa_available"])
        self.assertIsInstance(body["sessions"], list)
        self.assertTrue(any(e["kind"] == "login_success" for e in body["history"]))
        # No raw session key is ever exposed.
        for s in body["sessions"]:
            self.assertNotIn("session_key", s)

    def test_revoke_unknown_session_is_404(self):
        resp = self.client.post(
            reverse("settings_api:session-revoke", args=[999999]), **auth(self.user)
        )
        self.assertEqual(resp.status_code, 404)

    def test_revoke_own_session_succeeds(self):
        from apps.accounts.models import UserSession

        s = UserSession.objects.create(
            user=self.user, session_key="abc123", ip="1.2.3.4"
        )
        resp = self.client.post(
            reverse("settings_api:session-revoke", args=[s.id]), **auth(self.user)
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(UserSession.objects.filter(id=s.id).exists())

    def test_cannot_revoke_another_users_session(self):
        from apps.accounts.models import UserSession

        other = User.objects.create_user(email="other@x.com", password="pw12345!")
        s = UserSession.objects.create(
            user=other, session_key="other-key", ip="9.9.9.9"
        )
        resp = self.client.post(
            reverse("settings_api:session-revoke", args=[s.id]), **auth(self.user)
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(UserSession.objects.filter(id=s.id).exists())


class SecurityCenterPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="secweb@x.com", password="pw12345!", full_name="Sec Web"
        )

    def test_security_center_renders(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("dashboard:security_center"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Active sessions")
        self.assertContains(r, "Recent activity")

    def test_revoke_via_page_post(self):
        from apps.accounts.models import UserSession

        self.client.force_login(self.user)
        s = UserSession.objects.create(
            user=self.user, session_key="page-key", ip="1.1.1.1"
        )
        r = self.client.post(
            reverse("dashboard:security_center"),
            {"action": "revoke", "session": s.id},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(UserSession.objects.filter(id=s.id).exists())


class _FakeRequest:
    """Minimal request stand-in for recording events without a full HTTP cycle."""

    META = {"HTTP_USER_AGENT": "Mozilla/5.0 (Macintosh) Chrome/120", "REMOTE_ADDR": "1.2.3.4"}


class MfaApiTests(TestCase):
    """The MFA management endpoints the Security Center (web + mobile) calls."""

    def setUp(self):
        self.user = User.objects.create_user(email="mfaapi@x.com", password="pw12345!")

    def _totp_now(self):
        import pyotp

        from apps.accounts.models import TotpDevice

        return pyotp.TOTP(TotpDevice.objects.get(user=self.user).secret).now()

    def test_enroll_returns_secret_uri_and_qr(self):
        resp = self.client.post(reverse("settings_api:mfa-enroll"), **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("secret", body)
        self.assertIn("otpauth://", body["otpauth_uri"])
        self.assertIn("<svg", body["qr_svg"])

    def test_confirm_enables_and_returns_recovery_codes(self):
        self.client.post(reverse("settings_api:mfa-enroll"), **auth(self.user))
        resp = self.client.post(
            reverse("settings_api:mfa-confirm"),
            data={"code": self._totp_now()},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["recovery_codes"]), 10)

    def test_confirm_with_bad_code_is_400(self):
        self.client.post(reverse("settings_api:mfa-enroll"), **auth(self.user))
        resp = self.client.post(
            reverse("settings_api:mfa-confirm"),
            data={"code": "000000"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(resp.status_code, 400)

    def test_disable_requires_correct_password(self):
        from apps.accounts import mfa

        mfa.begin_enrollment(self.user)
        mfa.confirm_enrollment(self.user, self._totp_now())
        bad = self.client.post(
            reverse("settings_api:mfa-disable"),
            data={"password": "wrong"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(bad.status_code, 400)
        self.assertTrue(mfa.is_enabled(self.user))
        ok = self.client.post(
            reverse("settings_api:mfa-disable"),
            data={"password": "pw12345!"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(mfa.is_enabled(self.user))

    def test_regenerate_recovery_codes_requires_password_and_mfa(self):
        from apps.accounts import mfa

        # Not enabled yet -> 400.
        early = self.client.post(
            reverse("settings_api:mfa-recovery-codes"),
            data={"password": "pw12345!"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(early.status_code, 400)
        mfa.begin_enrollment(self.user)
        mfa.confirm_enrollment(self.user, self._totp_now())
        resp = self.client.post(
            reverse("settings_api:mfa-recovery-codes"),
            data={"password": "pw12345!"},
            content_type="application/json",
            **auth(self.user),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["recovery_codes"]), 10)

    def test_enroll_requires_auth(self):
        resp = self.client.post(reverse("settings_api:mfa-enroll"))
        self.assertEqual(resp.status_code, 401)


class SettingsSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="search@x.com", password="pw12345!")

    def test_service_search_matches_label_key_scope(self):
        from apps.settings import service

        self.assertTrue(any(r["key"] == "security"
                            for r in service.search("security")))
        self.assertTrue(any(r["scope"] == "organization"
                            for r in service.search("organization")))
        # Blank query returns the whole catalog.
        self.assertEqual(len(service.search("")),
                         sum(len(v) for v in service.sections_catalog().values()))

    def test_search_api_filters_and_strips_routes(self):
        resp = self.client.get(reverse("settings_api:search"), {"q": "audit"},
                               **auth(self.user))
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(results)
        self.assertTrue(all("audit" in (r["label"] + r["key"]).lower() for r in results))
        for r in results:
            self.assertNotIn("route", r)

    def test_search_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("settings_api:search")).status_code, 401
        )


class SettingsCatalogAcceptanceTests(TestCase):
    """Acceptance sweep: the catalog and its wiring must stay internally
    consistent, so no section is advertised as available without a real
    destination."""

    def test_every_available_account_and_org_section_has_a_resolvable_route(self):
        from django.urls import reverse as url_reverse

        from apps.settings import service

        catalog = service.sections_catalog()
        for scope in ("account", "organization"):
            for s in catalog[scope]:
                if s.get("available"):
                    self.assertIn("route", s,
                                  f"{scope}.{s['key']} is available but has no route")
                    url_reverse(s["route"])  # raises NoReverseMatch if broken

    def test_available_project_sections_declare_their_scope(self):
        from apps.settings import service

        for s in service.sections_catalog()["project"]:
            if s.get("available"):
                # Project sections live in the project workspace: they carry a
                # scope_note (or an explicit route) rather than a global url.
                self.assertTrue(s.get("scope_note") or s.get("route"),
                                f"project.{s['key']} is available but unscoped")

    def test_overview_api_never_leaks_web_routes(self):
        user = User.objects.create_user(email="acc@x.com", password="pw12345!")
        body = self.client.get(reverse("settings_api:overview"), **auth(user)).json()
        for sections in body["sections"].values():
            for s in sections:
                self.assertNotIn("route", s)
