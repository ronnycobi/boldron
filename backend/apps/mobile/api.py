"""Mobile engine API (spec §5, §48) — the DESCRIBE → UNDERSTAND → PLAN front.

Authenticated, read-only planning endpoints over the mobile capability registry and
planner. They never trigger a build, signing or submission (those are gated, real
steps owned by apps.release) — they return the honest plan for a described app.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.mobile import capabilities as caps
from apps.mobile import planner


class MobileCapabilitiesView(APIView):
    """The full mobile capability catalogue, grouped, with honest status and the
    device permissions each capability requires."""

    def get(self, request):
        groups = []
        for group, items in caps.by_group():
            groups.append({
                "group": group,
                "items": [{
                    "id": c.id, "name": c.name, "status": c.status,
                    "generated": c.is_generated, "summary": c.summary,
                    "permissions": list(c.permissions),
                    "platform_notes": c.platform_notes,
                } for c in items],
            })
        return Response({
            "groups": groups,
            "permissions": [{"id": p.id, "name": p.name, "rationale": p.rationale}
                            for p in caps.PERMISSIONS.values()],
        })


class MobilePlanView(APIView):
    """Plan a mobile app from a plain-language brief. GET ?brief=… (optional
    ?platforms=ios,android,huawei) or POST {brief, platforms:[...]}."""

    def get(self, request):
        brief = request.query_params.get("brief", "")
        raw = request.query_params.get("platforms", "")
        platforms = [p for p in raw.split(",") if p] or None
        return Response(planner.plan(brief, platforms=platforms))

    def post(self, request):
        brief = request.data.get("brief", "")
        platforms = request.data.get("platforms") or None
        return Response(planner.plan(brief, platforms=platforms))
