"""Comment + mention service (spec §4).

Post a comment, resolve @mentions to real org members, and notify them. A mention is
resolved only to a member of the comment's org — by the email local-part typed as
`@handle`, or by an explicit list of member emails — so a mention never reaches an
arbitrary address, and tenant isolation holds.
"""
from __future__ import annotations

import re

from apps.audit.service import record as audit

_MENTION_RE = re.compile(r"@([A-Za-z0-9._%+-]+)")   # @handle (email local-part)


class CommentError(Exception):
    pass


def _org_members(organization):
    from apps.organizations.models import Membership
    return (Membership.objects.filter(organization=organization)
            .select_related("user"))


def _resolve_mentions(organization, body, extra_emails=None):
    """Return the set of org-member users mentioned by @handle in the body or named
    in extra_emails. Only members of this org resolve (tenant-safe)."""
    members = {m.user for m in _org_members(organization) if m.user}
    by_local = {}
    by_email = {}
    for u in members:
        email = (u.email or "").lower()
        by_email[email] = u
        local = email.split("@", 1)[0]
        by_local.setdefault(local, u)   # first wins on a collision
    mentioned = set()
    for handle in _MENTION_RE.findall(body or ""):
        u = by_local.get(handle.lower())
        if u:
            mentioned.add(u)
    for email in (extra_emails or []):
        u = by_email.get((email or "").lower())
        if u:
            mentioned.add(u)
    return mentioned


def post_comment(project, author, body, *, change=None, mention_emails=None):
    from apps.comments.models import Comment, CommentMention
    body = (body or "").strip()
    if not body:
        raise CommentError("A comment can't be empty.")
    comment = Comment.objects.create(
        project=project, change=change, author=author, body=body[:5000])

    mentioned = _resolve_mentions(project.organization, body, mention_emails)
    mentioned.discard(author)   # don't notify yourself
    for user in mentioned:
        mention = CommentMention.objects.create(comment=comment, user=user)
        _notify(comment, user, mention)

    audit("comment.post", actor=author, organization=project.organization,
          target=f"project:{project.id}",
          summary=f"commented{' (mentioned %d)' % len(mentioned) if mentioned else ''}")
    return comment


def _notify(comment, user, mention):
    """Email a mentioned member (best-effort). The mention record stands regardless."""
    if not user.email:
        return
    try:
        from apps.notifications.email import send_email
        author = comment.author.display_name if comment.author else "Someone"
        sent = send_email(
            subject=f"{author} mentioned you on {comment.project.name}",
            to=user.email,
            text=(f"{author} mentioned you in a comment on {comment.project.name}:\n\n"
                  f"{comment.body}\n\n"
                  f"Open it: /app/projects/{comment.project.id}/comments/\n"))
        if sent:
            mention.notified = True
            mention.save(update_fields=["notified"])
    except Exception:
        pass


def comments_for(project, *, change=None):
    qs = project.comments.select_related("author").prefetch_related("mentions__user")
    if change is not None:
        qs = qs.filter(change=change)
    return list(qs)
