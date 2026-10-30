"""Comments API (spec §4, §24) — one source of truth web + mobile consume.

Read a project's comments; post one (any org member). Mentions resolve only to org
members; the view is tenant-isolated.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comments import service
from apps.projects.access import project_for_read


def _comment_dict(c) -> dict:
    return {
        "id": c.id,
        "author": c.author.display_name if c.author else "Unknown",
        "author_id": c.author_id,
        "body": c.body,
        "change": c.change_id,
        "created_at": c.created_at.isoformat(),
        "mentions": [m.user.display_name for m in c.mentions.all()],
    }


class ProjectCommentsView(APIView):
    """GET the project's comments; POST a new one (members can comment)."""

    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        change_id = request.query_params.get("change")
        change = None
        if change_id:
            change = project.changes.filter(pk=change_id).first()
        return Response({
            "members": [
                {"name": m.user.display_name,
                 "handle": (m.user.email or "").split("@", 1)[0]}
                for m in service._org_members(project.organization) if m.user
            ],
            "comments": [_comment_dict(c) for c in service.comments_for(project, change=change)],
        })

    def post(self, request, project_pk):
        # Any org member may comment (read-access is membership).
        project = project_for_read(request.user, project_pk)
        change = None
        if request.data.get("change"):
            change = project.changes.filter(pk=request.data["change"]).first()
        try:
            comment = service.post_comment(
                project, request.user, request.data.get("body", ""),
                change=change, mention_emails=request.data.get("mention_emails"))
        except service.CommentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_comment_dict(comment), status=201)
