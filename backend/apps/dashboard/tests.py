from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.organizations.models import Organization, Role
from apps.orchestrator.models import AgentTask
from apps.projects.models import Project

User = get_user_model()


class LoginPageTests(TestCase):
    def test_login_page_offers_reset_and_signup(self):
        html = self.client.get(reverse("dashboard:login")).content.decode()
        self.assertIn(reverse("dashboard:password_reset"), html)
        self.assertIn(reverse("marketing:signup"), html)

    def test_staff_and_customers_land_in_the_right_place(self):
        User.objects.create_user(email="cust@x.com", password="pw12345678")
        r = self.client.post(reverse("dashboard:login"),
                             {"username": "cust@x.com", "password": "pw12345678"})
        self.assertRedirects(r, reverse("dashboard:home"), fetch_redirect_response=False)
        self.client.logout()
        User.objects.create_user(email="staff@x.com", password="pw12345678", is_staff=True)
        r = self.client.post(reverse("dashboard:login"),
                             {"username": "staff@x.com", "password": "pw12345678"})
        self.assertRedirects(r, reverse("console:overview"), fetch_redirect_response=False)

    def test_remember_me_controls_session_lifetime(self):
        User.objects.create_user(email="rm@x.com", password="pw12345678")
        self.client.post(reverse("dashboard:login"),
                         {"username": "rm@x.com", "password": "pw12345678"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())  # not remembered
        self.client.logout()
        self.client.post(reverse("dashboard:login"),
                         {"username": "rm@x.com", "password": "pw12345678", "remember": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())  # remembered


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reset@x.com", password="oldpass12345")

    def test_request_sends_one_branded_email_with_a_link(self):
        r = self.client.post(reverse("dashboard:password_reset"), {"email": "reset@x.com"})
        self.assertRedirects(r, reverse("dashboard:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("reset@x.com", msg.to)
        self.assertIn("/reset/", msg.body)                 # the confirm link
        self.assertIn("Application", msg.subject)          # branded (default APP_NAME)

    def test_unknown_email_is_not_revealed_and_sends_nothing(self):
        r = self.client.post(reverse("dashboard:password_reset"), {"email": "nobody@x.com"})
        self.assertRedirects(r, reverse("dashboard:password_reset_done"))  # same page
        self.assertEqual(len(mail.outbox), 0)              # no account -> no email

    def test_full_flow_sets_a_new_password_and_signs_in(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse("dashboard:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        # GET moves the token into the session and redirects to the set-password form.
        r = self.client.get(url, follow=True)
        self.assertContains(r, "Set a new password")
        set_url = r.redirect_chain[-1][0]
        r2 = self.client.post(set_url, {"new_password1": "brandnewpw42", "new_password2": "brandnewpw42"})
        self.assertRedirects(r2, reverse("dashboard:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandnewpw42"))
        self.assertTrue(self.client.login(username="reset@x.com", password="brandnewpw42"))

    def test_used_or_bad_token_shows_expired(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse("dashboard:password_reset_confirm",
                      kwargs={"uidb64": uid, "token": "bad-token"})
        r = self.client.get(url, follow=True)
        self.assertContains(r, "Link expired")


class DashboardUITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="z@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_login_required(self):
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_dashboard_lists_member_projects(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "App")

    def test_owner_creates_project_via_ui(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("dashboard:projects"),
            {"action": "create_project", "name": "New Site", "organization": self.org.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Project.objects.filter(name="New Site").exists())

    def test_member_cannot_create_project(self):
        self.client.force_login(self.member)
        self.client.post(
            reverse("dashboard:projects"),
            {"action": "create_project", "name": "Nope", "organization": self.org.id},
        )
        self.assertFalse(Project.objects.filter(name="Nope").exists())

    def test_overview_and_key_pages_render(self):
        self.client.force_login(self.member)
        for name in ["home", "projects", "agents", "tasks", "deployments", "usage"]:
            self.assertEqual(self.client.get(reverse("dashboard:" + name)).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("dashboard:soon", args=["monitoring"])).status_code, 200
        )

    def test_project_workspace_renders(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("dashboard:project", args=[self.project.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Built-in capabilities")
        self.assertContains(resp, "Build activity")

    def test_owner_queues_task_via_ui(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("dashboard:project", args=[self.project.id]),
            {"action": "create_task", "agent_key": "requirements", "brief": "x"},
        )
        self.assertEqual(
            AgentTask.objects.filter(project=self.project, agent_key="requirements").count(), 1
        )

    def test_owner_selects_stack_via_ui(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("dashboard:project", args=[self.project.id]),
            {"action": "select_stack", "backend": "django", "frontend": "react"},
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.technology["backend"], "django")
        self.assertEqual(self.project.technology["frontend"], "react")

    def test_cannot_open_foreign_project(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(reverse("dashboard:project", args=[self.project.id]))
        self.assertEqual(resp.status_code, 404)


class SecurityPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="so@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="sm@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_page_lists_projects(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("dashboard:security"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "App")

    def test_owner_runs_scan_and_findings_appear(self):
        import tempfile
        from django.test import override_settings
        from apps.repositories.service import repo_for_project
        from apps.project_context.models import ContextEntry, ContextKind

        self.client.force_login(self.owner)
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
                repo = repo_for_project(self.project)
                repo.init()
                repo.write_files({"app.py": "API_KEY = 'sk-live-abc123456'\nx = eval(v)\n"})
                repo.commit("seed")
                resp = self.client.post(
                    reverse("dashboard:security"),
                    {"action": "run_scan", "project": self.project.id},
                    follow=True,
                )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            ContextEntry.objects.filter(project=self.project, kind=ContextKind.SECURITY).exists()
        )

    def test_member_cannot_run_scan(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("dashboard:security"),
            {"action": "run_scan", "project": self.project.id},
            follow=True,
        )
        self.assertContains(resp, "Owner or admin")


class PeopleUITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="po@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="pm@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_page_lists_members(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("dashboard:people"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "po@x.com")

    def test_owner_invites_and_link_shown(self):
        from apps.organizations.models import Invitation
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("dashboard:people"),
            {"action": "invite", "organization": self.org.id,
             "email": "new@x.com", "role": "admin"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        inv = Invitation.objects.get(email="new@x.com", organization=self.org)
        self.assertContains(resp, inv.token)  # accept link surfaced

    def test_member_cannot_invite(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("dashboard:people"),
            {"action": "invite", "organization": self.org.id, "email": "x@x.com"},
            follow=True,
        )
        self.assertContains(resp, "Owner or admin")

    def test_owner_creates_team(self):
        from apps.organizations.models import Team
        self.client.force_login(self.owner)
        self.client.post(
            reverse("dashboard:people"),
            {"action": "create_team", "organization": self.org.id, "name": "Platform"},
        )
        self.assertTrue(Team.objects.filter(organization=self.org, name="Platform").exists())

    def test_accept_invite_flow(self):
        from apps.organizations import invitations
        invite = invitations.create_invitation(self.org, "joiner@x.com", invited_by=self.owner)
        joiner = User.objects.create_user(email="joiner@x.com", password="pw12345!")
        self.client.force_login(joiner)
        resp = self.client.get(reverse("dashboard:accept_invite", args=[invite.token]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            self.org.memberships.filter(user=joiner).exists()  # membership created
        )


class RealPagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rp@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        Project.objects.create(organization=self.org, name="App", created_by=self.user)
        self.client.force_login(self.user)

    def test_all_former_soon_links_render_real_pages(self):
        named = ["templates", "repository", "settings"]
        for name in named:
            r = self.client.get(reverse(f"dashboard:{name}"))
            self.assertEqual(r.status_code, 200, name)
            self.assertNotContains(r, "coming soon")
        for slug in ["apis", "database", "tests", "code-issues"]:
            r = self.client.get(reverse("dashboard:section", args=[slug]))
            self.assertEqual(r.status_code, 200, slug)
            self.assertNotContains(r, "coming soon")
        for area in ["environments", "cloud", "logs", "monitoring", "incidents",
                     "scaling", "performance", "infrastructure", "modernization"]:
            r = self.client.get(reverse("dashboard:ops", args=[area]))
            self.assertEqual(r.status_code, 200, area)
            self.assertNotContains(r, "coming soon")

    def test_settings_rename_and_delete(self):
        p = Project.objects.create(organization=self.org, name="Temp", created_by=self.user)
        self.client.post(reverse("dashboard:settings"),
                         {"action": "rename", "project": p.id, "name": "Renamed", "description": "d"})
        p.refresh_from_db()
        self.assertEqual(p.name, "Renamed")
        self.client.post(reverse("dashboard:settings"), {"action": "delete", "project": p.id})
        self.assertFalse(Project.objects.filter(pk=p.id).exists())

    def test_unknown_section_404(self):
        self.assertEqual(self.client.get(reverse("dashboard:section", args=["nope"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("dashboard:ops", args=["nope"])).status_code, 404)


class MachineryLeakGuardTests(TestCase):
    """The customer dashboard must not expose the internal agent machinery."""
    def setUp(self):
        self.user = User.objects.create_user(email="lg@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App", created_by=self.user)
        self.client.force_login(self.user)

    def test_ai_page_hides_capabilities_and_topology(self):
        r = self.client.get(reverse("dashboard:agents"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        for term in ["write_backend", "use_sandbox", "review_code", "write_migrations",
                     "use_repository", "least-privilege", "orchestrat", "capability"]:
            self.assertNotIn(term, body, term)

    def test_project_page_has_no_agent_roster_picker(self):
        body = self.client.get(reverse("dashboard:project", args=[self.project.id])).content.decode()
        self.assertNotIn('name="agent_key"', body)  # no roster dropdown
        for term in ["write_backend", "use_sandbox", "least-privilege"]:
            self.assertNotIn(term, body, term)


class BuilderHomeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="b@x.com", password="pw12345!",
                                              email_verified=True)
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)
        self.client.force_login(self.user)

    def test_home_is_the_builder(self):
        r = self.client.get(reverse("dashboard:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "What do you want to build?")
        self.assertContains(r, "Start with an example")
        # No internal machinery on the customer's landing page.
        for term in ["write_backend", "least-privilege", "orchestrat", "model router", "code_review"]:
            self.assertNotContains(r, term)

    def test_build_creates_project_and_starts_work(self):
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
                r = self.client.post(reverse("dashboard:home"),
                                     {"action": "build",
                                      "brief": "Build a CRM for my sales team with leads and deals."},
                                     follow=True)
        self.assertEqual(r.status_code, 200)
        p = Project.objects.filter(organization=self.org).order_by("-id").first()
        self.assertIsNotNone(p)
        self.assertTrue(p.name)                       # a name derived from the brief
        self.assertTrue(AgentTask.objects.filter(project=p).exists())  # build kicked off

    def test_build_auto_selects_a_stack_so_users_need_not_choose(self):
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as tmp, override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
            self.client.post(reverse("dashboard:home"),
                             {"action": "build", "brief": "Build an online store with cart and checkout."},
                             follow=True)
        p = Project.objects.filter(organization=self.org).order_by("-id").first()
        self.assertTrue((p.technology or {}).get("backend"))   # chosen for the user
        self.assertTrue((p.technology or {}).get("database"))

    def test_empty_brief_rejected(self):
        r = self.client.post(reverse("dashboard:home"), {"action": "build", "brief": "  "}, follow=True)
        self.assertContains(r, "Tell Application what you want to build")


class FriendlyLabelTests(TestCase):
    def test_maps_internal_keys_to_outcomes(self):
        from apps.dashboard.labels import friendly_step
        self.assertEqual(friendly_step("code_review"), "Quality review")
        self.assertEqual(friendly_step("database"), "Setting up your data")
        self.assertEqual(friendly_step("backend"), "Building the core features")
        self.assertEqual(friendly_step("weird-unknown"), "Working on your application")


class PreviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="pv@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="App", created_by=self.owner)
        self.client.force_login(self.owner)

    def test_preview_renders_two_panes(self):
        from apps.project_context.services import ProjectContext
        from apps.project_context.models import ContextKind
        ProjectContext(self.project).set(
            ContextKind.SCREEN, "dashboard", title="Dashboard",
            data={"route": "/", "components": ["Chart", "Table"], "platform": "web"},
        )
        r = self.client.get(reverse("dashboard:preview", args=[self.project.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ask Application")   # chat control (brand from APP_NAME)
        self.assertContains(r, "Dashboard")         # screen wireframe from the twin
        self.assertContains(r, "design preview")    # honest label, not a fake running app

    def test_preview_chat_creates_change(self):
        import tempfile
        from django.test import override_settings
        from apps.changes.models import ChangeRequest
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BOLDRON_WORKSPACES_ROOT=tmp):
                self.client.post(reverse("dashboard:preview", args=[self.project.id]),
                                 {"message": "add customer search"}, follow=True)
        self.assertTrue(ChangeRequest.objects.filter(project=self.project).exists())


class PeopleManagementViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="po@x.com", password="pw12345678")
        self.member = User.objects.create_user(email="pm@x.com", password="pw12345678")
        self.org = Organization.objects.create(name="Acme", created_by=self.owner)
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_owner_can_promote_and_remove_via_people_page(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("dashboard:people"), {
            "action": "set_role", "organization": self.org.id,
            "user": self.member.id, "role": Role.ADMIN})
        from apps.organizations.models import Membership
        self.assertEqual(Membership.objects.get(organization=self.org, user=self.member).role, Role.ADMIN)
        self.client.post(reverse("dashboard:people"), {
            "action": "remove_member", "organization": self.org.id, "user": self.member.id})
        self.assertFalse(Membership.objects.filter(organization=self.org, user=self.member).exists())

    def test_plain_member_cannot_manage_but_can_leave(self):
        self.client.force_login(self.member)
        # Not a manager → role change is refused.
        self.client.post(reverse("dashboard:people"), {
            "action": "set_role", "organization": self.org.id,
            "user": self.owner.id, "role": Role.MEMBER})
        from apps.organizations.models import Membership
        self.assertEqual(Membership.objects.get(organization=self.org, user=self.owner).role, Role.OWNER)
        # But they can leave.
        self.client.post(reverse("dashboard:people"), {"action": "leave", "organization": self.org.id})
        self.assertFalse(Membership.objects.filter(organization=self.org, user=self.member).exists())


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@x.com", password="oldpass12345", full_name="Me")

    def _login(self):
        self.assertTrue(self.client.login(username="me@x.com", password="oldpass12345"))

    def test_update_profile_name_and_email(self):
        self._login()
        self.client.post(reverse("dashboard:account"),
                         {"action": "profile", "full_name": "New Name", "email": "new@x.com"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "New Name")
        self.assertEqual(self.user.email, "new@x.com")

    def test_email_change_rejects_duplicate(self):
        User.objects.create_user(email="taken@x.com", password="x")
        self._login()
        self.client.post(reverse("dashboard:account"),
                         {"action": "profile", "full_name": "Me", "email": "taken@x.com"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "me@x.com")  # unchanged

    def test_change_password_success_keeps_this_session(self):
        self._login()
        self.client.post(reverse("dashboard:account"),
                         {"action": "password", "old_password": "oldpass12345",
                          "new_password1": "brandnewpw99", "new_password2": "brandnewpw99"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandnewpw99"))
        self.assertEqual(self.client.get(reverse("dashboard:account")).status_code, 200)  # still in

    def test_change_password_wrong_current_is_rejected(self):
        self._login()
        self.client.post(reverse("dashboard:account"),
                         {"action": "password", "old_password": "WRONG",
                          "new_password1": "brandnewpw99", "new_password2": "brandnewpw99"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("oldpass12345"))  # unchanged

    def test_sign_out_other_sessions(self):
        from django.test import Client
        other = Client(); other.login(username="me@x.com", password="oldpass12345")
        me = Client(); me.login(username="me@x.com", password="oldpass12345")
        self.assertEqual(other.get(reverse("dashboard:account")).status_code, 200)
        me.post(reverse("dashboard:account"), {"action": "sessions"})
        self.assertEqual(other.get(reverse("dashboard:account")).status_code, 302)  # signed out
        self.assertEqual(me.get(reverse("dashboard:account")).status_code, 200)     # kept


class LoginLockoutTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_user(email="lock@x.com", password="rightpass123")

    def _fail(self):
        return self.client.post(reverse("dashboard:login"),
                                {"username": "lock@x.com", "password": "wrong"})

    def test_locks_after_five_failures(self):
        for _ in range(5):
            self._fail()
        # 6th attempt is blocked even with the CORRECT password.
        r = self.client.post(reverse("dashboard:login"),
                             {"username": "lock@x.com", "password": "rightpass123"})
        self.assertEqual(r.status_code, 200)             # re-rendered, not redirected
        self.assertContains(r, "Too many attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_before_lock_clears_the_counter(self):
        for _ in range(3):
            self._fail()
        r = self.client.post(reverse("dashboard:login"),
                             {"username": "lock@x.com", "password": "rightpass123"})
        self.assertEqual(r.status_code, 302)             # logged in, counter reset
        self.client.logout()
        for _ in range(3):
            self._fail()                                  # only 3 again -> still allowed
        r = self.client.post(reverse("dashboard:login"),
                             {"username": "lock@x.com", "password": "rightpass123"})
        self.assertEqual(r.status_code, 302)             # not locked


class PasswordResetThrottleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)

    def test_reset_requests_are_rate_limited(self):
        for _ in range(8):
            self.client.post(reverse("dashboard:password_reset"), {"email": "spam@x.com"})
        r = self.client.post(reverse("dashboard:password_reset"), {"email": "spam@x.com"})
        self.assertContains(r, "Too many attempts")


class EmailVerificationTests(TestCase):
    def setUp(self):
        # New accounts start unverified.
        self.user = User.objects.create_user(email="unv@x.com", password="pw12345678")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.user, role=Role.OWNER)

    def test_unverified_user_cannot_build(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("dashboard:home"),
                             {"action": "build", "brief": "Build a CRM"}, follow=True)
        self.assertContains(r, "verify your email")
        self.assertEqual(Project.objects.count(), 0)

    def test_dashboard_shows_banner_until_verified(self):
        from apps.accounts import verification
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("dashboard:home")), "Verify your email")
        verification.mark_verified(self.user)
        self.assertNotContains(self.client.get(reverse("dashboard:home")), "Verify your email")

    def test_verify_link_marks_verified(self):
        from apps.accounts import verification
        token = verification.make_token(self.user)
        r = self.client.get(reverse("dashboard:verify_email", args=[token]))
        self.assertContains(r, "Email verified")
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_invalid_token_is_rejected(self):
        r = self.client.get(reverse("dashboard:verify_email", args=["not-a-real-token"]))
        self.assertContains(r, "invalid")
        self.assertFalse(User.objects.get(pk=self.user.pk).email_verified)

    def test_token_bound_to_email_breaks_if_email_changes(self):
        from apps.accounts import verification
        token = verification.make_token(self.user)
        self.user.email = "moved@x.com"
        self.user.save(update_fields=["email"])
        user, reason = verification.verify(token)
        self.assertIsNone(user)

    def test_resend_sends_an_email(self):
        self.client.force_login(self.user)
        self.client.post(reverse("dashboard:resend_verification"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("unv@x.com", mail.outbox[0].to)


class SettingsHubTests(TestCase):
    def setUp(self):
        from apps.credits.services import ensure_account
        self.owner = User.objects.create_user(email="so@x.com", password="pw12345678", email_verified=True)
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        ensure_account(self.org, plan="free")  # grants the free allowance (1000)
        self.client.force_login(self.owner)

    def test_plan_tab_shows_plan_credits_and_features(self):
        r = self.client.get(reverse("dashboard:settings"))
        self.assertContains(r, "AI credit balance")
        self.assertContains(r, "What's included")
        self.assertContains(r, "1000")                 # free allowance
        self.assertContains(r, "Request")              # an upgrade CTA

    def test_save_preferences_persists(self):
        self.client.post(reverse("dashboard:settings"),
                         {"action": "save_preferences", "language": "fr", "timezone": "Europe/London"})
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.language, "fr")
        self.assertEqual(self.owner.timezone, "Europe/London")

    def test_invalid_preferences_are_ignored(self):
        self.client.post(reverse("dashboard:settings"),
                         {"action": "save_preferences", "language": "zz-hack", "timezone": "Mars/Base"})
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.language, "")
        self.assertEqual(self.owner.timezone, "")

    def test_request_upgrade_creates_a_billing_ticket(self):
        from apps.support.models import SupportTicket
        self.client.post(reverse("dashboard:settings"),
                         {"action": "request_upgrade", "organization": self.org.id, "plan": "pro"})
        t = SupportTicket.objects.filter(organization=self.org, category="billing").first()
        self.assertIsNotNone(t)
        self.assertIn("Builder", t.subject)

    def test_member_cannot_request_upgrade(self):
        from apps.support.models import SupportTicket
        member = User.objects.create_user(email="sm@x.com", password="pw12345678", email_verified=True)
        self.org.add_member(member, role=Role.MEMBER)
        self.client.force_login(member)
        self.client.post(reverse("dashboard:settings"),
                         {"action": "request_upgrade", "organization": self.org.id, "plan": "pro"})
        self.assertEqual(SupportTicket.objects.filter(category="billing").count(), 0)


class ProfileAvatarTests(TestCase):
    def setUp(self):
        import shutil, tempfile
        from django.test import override_settings
        self.tmp = tempfile.mkdtemp()
        ov = override_settings(MEDIA_ROOT=self.tmp)
        ov.enable(); self.addCleanup(ov.disable)
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.user = User.objects.create_user(email="av@x.com", password="pw12345678", email_verified=True)
        self.client.force_login(self.user)

    def _png(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO(); Image.new("RGB", (12, 12), "blue").save(buf, "PNG")
        return SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png")

    def test_upload_sets_avatar(self):
        self.client.post(reverse("dashboard:account"), {"action": "avatar", "avatar": self._png()})
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)
        self.assertTrue(self.user.avatar_url)

    def test_non_image_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile("x.txt", b"not an image", content_type="text/plain")
        self.client.post(reverse("dashboard:account"), {"action": "avatar", "avatar": bad})
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_oversize_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("big.png", b"x" * (3 * 1024 * 1024 + 1), content_type="image/png")
        self.client.post(reverse("dashboard:account"), {"action": "avatar", "avatar": big})
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_remove_avatar(self):
        self.client.post(reverse("dashboard:account"), {"action": "avatar", "avatar": self._png()})
        self.client.post(reverse("dashboard:account"), {"action": "remove_avatar"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
