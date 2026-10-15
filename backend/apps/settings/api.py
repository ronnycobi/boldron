"""Settings API — the single backend both web and mobile consume.

P0 exposes the control-center overview (status + alerts + the section map).
Later phases add the per-section read/write endpoints under /api/v1/settings/.
"""
from __future__ import annotations

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
