"""Integrations API (mobile/API client) — spec §23.

Lists the integrations (connectors) the platform supports and whether each is
configured. Honest: `configured` reflects whether a real credential is present,
never a fabricated 'connected'. The credential env-var name is not exposed to
customers (that's operator configuration, not product surface).
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tools.connectors import connector_status


class IntegrationListView(APIView):
    def get(self, request):
        integrations = [
            {
                "key": c["key"],
                "provider": c["provider"],
                "configured": c["configured"],
                "actions": c["actions"],
            }
            for c in connector_status()
        ]
        return Response({"integrations": integrations})
