"""Comments & mentions (spec §4 — collaboration).

A comment is attached to a project (and optionally a specific change), authored by a
member, with @mentions of other org members who are notified. Collaboration is
tenant-isolated: only org members can read or post, and a mention only resolves to a
real member of the same org — never an arbitrary address.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Comment(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="comments")
    change = models.ForeignKey(
        "changes.ChangeRequest", on_delete=models.CASCADE, null=True, blank=True,
        related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="comments")
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["project", "created_at"])]

    def __str__(self):
        return f"comment by {self.author_id} on project {self.project_id}"


class CommentMention(models.Model):
    """A member mentioned in a comment (and whether they were notified)."""

    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="mentions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comment_mentions")
    notified = models.BooleanField(default=False)

    class Meta:
        unique_together = [("comment", "user")]

    def __str__(self):
        return f"mention of {self.user_id} in comment {self.comment_id}"
