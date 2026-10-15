"""Settings API — the single backend both web and mobile consume.

P0 exposes the control-center overview (status + alerts + the section map).
Later phases add the per-section read/write endpoints under /api/v1/settings/.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.settings import service


def _public_sections() -> dict:
    """The section map without web-only route names (mobile navigates by key)."""
    catalog = service.sections_catalog()
    cleaned: dict[str, list[dict]] = {}
    for scope, sections in catalog.items():
        cleaned[scope] = [
            {k: v for k, v in s.items() if k != "route"} for s in sections
        ]
    return cleaned


class SettingsOverviewView(APIView):
    """GET the signed-in user's settings overview: real alerts, account + org
    status, and the full section map with availability flags."""

    def get(self, request):
        data = service.overview(request.user)
        # Strip web route names from alerts/sections for API consumers.
        alerts = [
            {k: v for k, v in a.items() if k != "route"} for a in data["alerts"]
        ]
        return Response({
            "alerts": alerts,
            "account": data["account"],
            "organizations": data["organizations"],
            "sections": _public_sections(),
        })


class SecurityView(APIView):
    """Account Security Center (spec §9/§12/§13): status + active sessions +
    recent login history. Read-only; sensitive values are never returned."""

    def get(self, request):
        from apps.accounts import security

        user = request.user
        current = getattr(getattr(request, "session", None), "session_key", "") or ""
        sessions = security.active_sessions(user)
        history = [security.event_dict(e) for e in user.login_events.all()[:25]]
        return Response({
            "status": security.security_status(user),
            "sessions": [security.session_dict(s, current_key=current) for s in sessions],
            "history": history,
        })


class SessionRevokeView(APIView):
    """Revoke one of the user's own web sessions by its id."""

    def post(self, request, session_id):
        from apps.accounts import security

        ok = security.revoke_session_by_id(request.user, session_id, request=request)
        if not ok:
            return Response(
                {"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
