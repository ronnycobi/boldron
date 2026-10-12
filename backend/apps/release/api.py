"""Mobile Release Center API (mobile/API client).

Read + create surface over apps.release. Live store operations (submit, publish,
review sync) are NOT exposed here: every provider's is_available() is False until
the customer's own store credentials are connected on the host, and the platform
never fabricates a store connection or submission (spec §18/§50). The mobile app
can see identity, builds, per-store readiness and connection state, and create an
application; actually shipping to a store stays gated on real credentials.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.access import organizations_for
from apps.projects.access import project_for_read, require_manageable_project
from apps.release import service
from apps.release.models import MobileApplication, StoreConnection
from apps.release.providers import all_providers, get_provider

_PROVIDER_LABELS = {
    "google_play": "Google Play",
    "apple_app_store": "Apple App Store",
    "huawei_appgallery": "Huawei AppGallery",
}


def _app_dict(app: MobileApplication, *, detail=False) -> dict:
    data = {
        "id": app.id,
        "project": app.project_id,
        "name": app.name,
        "package_identifier": app.package_identifier,
        "bundle_identifier": app.bundle_identifier,
        "version": app.version,
        "build_number": app.build_number,
        "created_at": app.created_at.isoformat(),
    }
    if detail:
        data["builds"] = [
            {
                "id": b.id,
                "platform": b.platform,
                "version": b.version,
                "build_number": b.build_number,
                "artifact_format": b.artifact_format,
                "status": b.status,
                "detail": b.detail,
                "has_artifact": bool(b.artifact_path),
            }
            for b in app.builds.all()
        ]
        data["store_apps"] = [
            {
                "id": s.id,
                "provider": s.provider,
                "provider_label": _PROVIDER_LABELS.get(s.provider, s.provider),
                "metadata_status": s.metadata_status,
                "signing_status": s.signing_status,
                "release_status": s.release_status,
                "review_status": s.review_status,
            }
            for s in app.store_apps.all()
        ]
        data["signing"] = [
            {"platform": c.platform, "mode": c.mode, "configured": c.configured}
            for c in app.signing_configs.all()
        ]
    return data


class ProviderListView(APIView):
    """The configured app stores and whether live operations are possible. All
    are gated (available:false) until the customer connects store credentials."""

    def get(self, request):
        return Response(
            [
                {
                    "key": p.key,
                    "label": _PROVIDER_LABELS.get(p.key, p.key),
                    "available": p.is_available(),
                }
                for p in all_providers()
            ]
        )


class MobileAppListCreateView(APIView):
    def get(self, request, project_pk):
        project = project_for_read(request.user, project_pk)
        return Response([_app_dict(a) for a in project.mobile_applications.all()])

    def post(self, request, project_pk):
        project = require_manageable_project(request.user, project_pk)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"name": ["An app name is required."]},
                            status=status.HTTP_400_BAD_REQUEST)
        app = service.create_mobile_application(
            project=project,
            name=name,
            package_identifier=(request.data.get("package_identifier") or "").strip(),
            bundle_identifier=(request.data.get("bundle_identifier") or "").strip(),
        )
        return Response(_app_dict(app, detail=True), status=status.HTTP_201_CREATED)


class MobileAppDetailView(APIView):
    def get(self, request, pk):
        app = get_object_or_404(MobileApplication, pk=pk)
        if app.project.organization not in organizations_for(request.user):
            from django.http import Http404

            raise Http404
        return Response(_app_dict(app, detail=True))


class StoreConnectionListView(APIView):
    """An org's store connections — honest status (not_connected until real
    credentials are configured)."""

    def get(self, request, org_pk):
        org = get_object_or_404(organizations_for(request.user), pk=org_pk)
        connections = StoreConnection.objects.filter(organization=org)
        existing = {c.provider: c for c in connections}
        rows = []
        for p in all_providers():
            conn = existing.get(p.key)
            rows.append(
                {
                    "provider": p.key,
                    "label": _PROVIDER_LABELS.get(p.key, p.key),
                    "status": conn.status if conn else "not_connected",
                    "detail": conn.detail if conn else "No credentials connected.",
                    "live_available": p.is_available(),
                }
            )
        return Response(rows)
