"""Comments & mentions (spec §4): members comment, @mentions resolve only to org
members and notify them, and the thread is tenant-isolated."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.comments import service
from apps.comments.models import Comment, CommentMention
from apps.organizations.models import Organization, Role
from apps.projects.models import Project

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class CommentServiceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="CmtOrg")
        self.alice = User.objects.create_user(email="alice@x.com", password="pw12345!", full_name="Alice A")
        self.bob = User.objects.create_user(email="bob@x.com", password="pw12345!", full_name="Bob B")
        self.org.add_member(self.alice, role=Role.OWNER)
        self.org.add_member(self.bob, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_post_records_a_comment(self):
        c = service.post_comment(self.project, self.alice, "Looks good")
        self.assertIsInstance(c, Comment)
        self.assertEqual(c.author_id, self.alice.id)

    def test_empty_comment_rejected(self):
        with self.assertRaises(service.CommentError):
            service.post_comment(self.project, self.alice, "   ")

    def test_handle_mention_resolves_and_notifies_a_member(self):
        mail.outbox = []
        c = service.post_comment(self.project, self.alice, "Can you check this @bob?")
        self.assertTrue(CommentMention.objects.filter(comment=c, user=self.bob).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@x.com"])
        self.assertTrue(CommentMention.objects.get(comment=c, user=self.bob).notified)

    def test_mention_of_a_non_member_does_not_resolve(self):
        service.post_comment(self.project, self.alice, "Hey @stranger take a look")
        self.assertEqual(CommentMention.objects.count(), 0)

    def test_author_is_not_notified_for_mentioning_self(self):
        mail.outbox = []
        service.post_comment(self.project, self.alice, "note to @alice self")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(CommentMention.objects.count(), 0)

    def test_explicit_mention_emails_resolve_to_members_only(self):
        c = service.post_comment(self.project, self.alice, "fyi",
                                 mention_emails=["bob@x.com", "outsider@x.com"])
        mentioned = {m.user_id for m in c.mentions.all()}
        self.assertEqual(mentioned, {self.bob.id})   # only the member


class CommentApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!", full_name="Owner")
        self.member = User.objects.create_user(email="m@x.com", password="pw12345!", full_name="Mem Ber")
        self.outsider = User.objects.create_user(email="x@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="CApiOrg")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_member_can_post_and_list(self):
        create = self.client.post(
            reverse("comments_api:list", args=[self.project.id]),
            data={"body": "Hi team @o"}, content_type="application/json", **auth(self.member))
        self.assertEqual(create.status_code, 201)
        self.assertIn("Owner", create.json()["mentions"])   # @o -> owner
        listed = self.client.get(
            reverse("comments_api:list", args=[self.project.id]), **auth(self.owner))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["comments"]), 1)
        self.assertTrue(any(mm["handle"] == "o" for mm in listed.json()["members"]))

    def test_outsider_cannot_read(self):
        resp = self.client.get(
            reverse("comments_api:list", args=[self.project.id]), **auth(self.outsider))
        self.assertIn(resp.status_code, (403, 404))

    def test_empty_body_is_400(self):
        resp = self.client.post(
            reverse("comments_api:list", args=[self.project.id]),
            data={"body": ""}, content_type="application/json", **auth(self.owner))
        self.assertEqual(resp.status_code, 400)
