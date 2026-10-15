"""Tests for the organizations/teams API (mobile client)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Invitation, Organization, Role

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class OrganizationApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_list_only_my_orgs(self):
        resp = self.client.get(reverse("organizations:list"), **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        names = [o["name"] for o in resp.json()]
        self.assertEqual(names, ["Acme"])
        self.assertEqual(resp.json()[0]["role"], "member")
        self.assertFalse(resp.json()[0]["can_manage"])

    def test_create_org_makes_me_owner_with_account(self):
        from apps.credits.services import get_account

        resp = self.client.post(
            reverse("organizations:list"),
            data={"name": "New Org"},
            content_type="application/json",
            **auth(self.outsider),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["role"], "owner")
        org = Organization.objects.get(name="New Org")
        self.assertIsNotNone(get_account(org))

    def test_detail_denied_for_outsider(self):
        resp = self.client.get(
            reverse("organizations:detail", args=[self.org.id]), **auth(self.outsider)
        )
        self.assertEqual(resp.status_code, 404)  # tenant isolation: not even visible

    def test_rename_requires_manage(self):
        resp = self.client.patch(
            reverse("organizations:detail", args=[self.org.id]),
            data={"name": "Renamed"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_rename(self):
        resp = self.client.patch(
            reverse("organizations:detail", args=[self.org.id]),
            data={"name": "Acme Renamed"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Acme Renamed")

    def test_members_list(self):
        resp = self.client.get(
            reverse("organizations:members", args=[self.org.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_owner_changes_member_role(self):
        resp = self.client.patch(
            reverse("organizations:member-detail", args=[self.org.id, self.member.id]),
            data={"role": "admin"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], "admin")

    def test_cannot_remove_last_owner(self):
        resp = self.client.delete(
            reverse("organizations:member-detail", args=[self.org.id, self.owner.id]),
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 400)

    def test_member_can_leave(self):
        resp = self.client.post(
            reverse("organizations:leave", args=[self.org.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(self.org.memberships.filter(user=self.member).exists())

    def test_last_owner_cannot_leave(self):
        resp = self.client.post(
            reverse("organizations:leave", args=[self.org.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 400)


class InvitationApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)

    def test_create_and_list_invitation(self):
        resp = self.client.post(
            reverse("organizations:invitations", args=[self.org.id]),
            data={"email": "invitee@x.com", "role": "member"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["email"], "invitee@x.com")
        listed = self.client.get(
            reverse("organizations:invitations", args=[self.org.id]), **auth(self.owner)
        )
        self.assertEqual(len(listed.json()), 1)

    def test_revoke_invitation(self):
        inv = Invitation.objects.create(organization=self.org, email="i@x.com")
        resp = self.client.post(
            reverse("organizations:invitation-revoke", args=[self.org.id, inv.id]),
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "revoked")

    def test_accept_invitation_joins_org(self):
        invitee = User.objects.create_user(email="invitee@x.com", password="pw12345!")
        inv = Invitation.objects.create(
            organization=self.org, email="invitee@x.com", role=Role.MEMBER
        )
        resp = self.client.post(
            reverse("organizations:invitation-accept"),
            data={"token": inv.token},
            content_type="application/json",
            **auth(invitee),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.org.memberships.filter(user=invitee).exists())

    def test_accept_rejects_email_mismatch(self):
        stranger = User.objects.create_user(email="stranger@x.com", password="pw12345!")
        inv = Invitation.objects.create(
            organization=self.org, email="invitee@x.com", role=Role.MEMBER
        )
        resp = self.client.post(
            reverse("organizations:invitation-accept"),
            data={"token": inv.token},
            content_type="application/json",
            **auth(stranger),
        )
        self.assertEqual(resp.status_code, 400)

    def test_invitations_require_manage(self):
        member = User.objects.create_user(email="m@x.com", password="pw12345!")
        self.org.add_member(member, role=Role.MEMBER)
        resp = self.client.get(
            reverse("organizations:invitations", args=[self.org.id]), **auth(member)
        )
        self.assertEqual(resp.status_code, 403)


class OrgSettingsAndRolesApiTests(TestCase):
    """P2: org general settings (name+description) + the RBAC matrix endpoint."""

    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.admin = User.objects.create_user(email="a2@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="m2@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Beta")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.admin, role=Role.ADMIN)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_admin_can_edit_description(self):
        resp = self.client.patch(
            reverse("organizations:detail", args=[self.org.id]),
            data={"description": "We build things."},
            content_type="application/json",
            **auth(self.admin),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["description"], "We build things.")
        self.org.refresh_from_db()
        self.assertEqual(self.org.description, "We build things.")

    def test_member_cannot_edit_description(self):
        resp = self.client.patch(
            reverse("organizations:detail", args=[self.org.id]),
            data={"description": "nope"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.description, "")

    def test_detail_exposes_my_permissions(self):
        owner = self.client.get(
            reverse("organizations:detail", args=[self.org.id]), **auth(self.owner)
        ).json()
        member = self.client.get(
            reverse("organizations:detail", args=[self.org.id]), **auth(self.member)
        ).json()
        self.assertIn("ownership.manage", owner["my_permissions"])
        self.assertIn("org.manage", owner["my_permissions"])
        self.assertEqual(member["my_permissions"], [])

    def test_roles_matrix_endpoint(self):
        resp = self.client.get(
            reverse("organizations:roles", args=[self.org.id]), **auth(self.admin)
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["roles"]), 3)
        keys = {row["key"] for row in body["matrix"]}
        self.assertIn("org.manage", keys)
        # Admin holds management perms but not ownership.manage.
        self.assertIn("members.manage", body["my_permissions"])
        self.assertNotIn("ownership.manage", body["my_permissions"])
        # The matrix reflects the real role→permission mapping.
        ownership = next(r for r in body["matrix"] if r["key"] == "ownership.manage")
        self.assertTrue(ownership["roles"]["owner"])
        self.assertFalse(ownership["roles"]["admin"])
        self.assertFalse(ownership["roles"]["member"])

    def test_roles_requires_membership(self):
        outsider = User.objects.create_user(email="x2@x.com", password="pw12345!")
        resp = self.client.get(
            reverse("organizations:roles", args=[self.org.id]), **auth(outsider)
        )
        self.assertEqual(resp.status_code, 404)


class OrgAiApiTests(TestCase):
    """The per-org AI settings endpoint."""

    def setUp(self):
        self.owner = User.objects.create_user(email="aio@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="aim@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="AiCo")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_get_returns_options_and_generation(self):
        resp = self.client.get(
            reverse("organizations:ai", args=[self.org.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("preferences", body)
        self.assertIn("options", body)
        self.assertIn("live", body["generation"])
        self.assertFalse(body["can_manage"])  # member

    def test_member_cannot_change(self):
        resp = self.client.patch(
            reverse("organizations:ai", args=[self.org.id]),
            data={"preferred_provider": "anthropic"},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_sets_valid_preference(self):
        from apps.organizations import ai_settings

        provider = ai_settings.available_options()[0]["provider"]
        resp = self.client.patch(
            reverse("organizations:ai", args=[self.org.id]),
            data={"preferred_provider": provider},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["preferences"]["preferred_provider"], provider)

    def test_owner_unknown_provider_is_400(self):
        resp = self.client.patch(
            reverse("organizations:ai", args=[self.org.id]),
            data={"preferred_provider": "nope"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 400)


class AuditAndExportApiTests(TestCase):
    """Org audit log (read-only) + org/account data export."""

    def setUp(self):
        self.owner = User.objects.create_user(email="ax@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="mx@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Audited")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)

    def test_audit_log_manager_only(self):
        from apps.audit.service import record

        record("settings.test", actor=self.owner, organization=self.org, summary="hi")
        denied = self.client.get(
            reverse("organizations:audit", args=[self.org.id]), **auth(self.member)
        )
        self.assertEqual(denied.status_code, 403)
        ok = self.client.get(
            reverse("organizations:audit", args=[self.org.id]), **auth(self.owner)
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(any(e["action"] == "settings.test" for e in ok.json()["events"]))

    def test_org_export_manager_only_and_no_secrets(self):
        from apps.developer.models import ApiKey

        ApiKey.generate(self.org, "CI", created_by=self.owner)
        denied = self.client.get(
            reverse("organizations:export", args=[self.org.id]), **auth(self.member)
        )
        self.assertEqual(denied.status_code, 403)
        body = self.client.get(
            reverse("organizations:export", args=[self.org.id]), **auth(self.owner)
        ).json()
        self.assertEqual(body["organization"]["name"], "Audited")
        # API keys appear masked, never with a usable secret.
        self.assertTrue(body["api_keys"][0]["masked"].startswith("bk_"))
        self.assertNotIn("secret", body["api_keys"][0])

    def test_account_export(self):
        body = self.client.get(
            reverse("accounts:account-export"), **auth(self.member)
        ).json()
        self.assertEqual(body["account"]["email"], "mx@x.com")
        self.assertTrue(any(o["name"] == "Audited" for o in body["organizations"]))
