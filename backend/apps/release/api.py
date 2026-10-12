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


def _metadata_dict(md) -> dict | None:
    if md is None:
        return None
    gen = md.generated or {}
    return {
        "app_name": md.app_name,
        "short_description": md.short_description,
        "full_description": md.full_description,
        "keywords": md.keywords,
        "category": md.category,
        "ai_generated": md.ai_generated,
        "approved": md.approved,
        "feature_descriptions": gen.get("feature_descriptions", []),
        "screenshot_captions": gen.get("screenshot_captions", []),
        "source": gen.get("source", ""),
        "updated_at": md.updated_at.isoformat(),
    }


def _asset_dict(a) -> dict:
    return {
        "id": a.id,
        "screen_name": a.screen_name,
        "caption": a.caption,
        "width": a.width,
        "height": a.height,
        "source": a.source,
        "fmt": a.fmt,
        "approved": a.approved,
    }


def _valid_provider(provider: str):
    """Return the provider instance or None (unknown key)."""
    return get_provider(provider)


class StoreListingView(APIView):
    """A store listing (metadata) for one app + provider.

    GET reads the current draft + screenshots (member). POST generates an
    AI-assisted draft from the app's real features — marked ai_generated and
    NOT approved; a human must approve before anything could be submitted
    (manager). Nothing is auto-submitted and live store ops stay gated.
    """

    def _store_app(self, request, pk, provider, *, manage):
        if _valid_provider(provider) is None:
            return None, Response(
                {"detail": "Unknown store provider."},
                status=status.HTTP_404_NOT_FOUND,
            )
        app = get_object_or_404(MobileApplication, pk=pk)
        if manage:
            require_manageable_project(request.user, app.project_id)
        else:
            if app.project.organization not in organizations_for(request.user):
                from django.http import Http404

                raise Http404
        return app, None

    def get(self, request, pk, provider):
        app, err = self._store_app(request, pk, provider, manage=False)
        if err:
            return err
        store_app = app.store_apps.filter(provider=provider).first()
        md = getattr(store_app, "metadata", None) if store_app else None
        screenshots = (
            [_asset_dict(a) for a in store_app.assets.filter(kind="screenshot")]
            if store_app
            else []
        )
        return Response(
            {
                "provider": provider,
                "provider_label": _PROVIDER_LABELS.get(provider, provider),
                "metadata": _metadata_dict(md),
                "screenshots": screenshots,
            }
        )

    def post(self, request, pk, provider):
        app, err = self._store_app(request, pk, provider, manage=True)
        if err:
            return err
        store_app = service.ensure_store_application(app, provider)
        md = service.generate_store_listing(store_app, user=request.user)
        return Response(_metadata_dict(md), status=status.HTTP_201_CREATED)


class StoreListingApproveView(APIView):
    """Approve a listing draft (a human sign-off; never automatic)."""

    def post(self, request, pk, provider):
        app = get_object_or_404(MobileApplication, pk=pk)
        require_manageable_project(request.user, app.project_id)
        store_app = app.store_apps.filter(provider=provider).first()
        if store_app is None:
            return Response(
                {"detail": "Generate a listing before approving it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        md = service.approve_metadata(store_app, user=request.user)
        return Response(_metadata_dict(md))


class StoreScreenshotsView(APIView):
    """Generate (POST) store screenshots from the app's real screens. Honest
    scope: schematic layout previews unless live-capture infra is wired; drafts,
    never auto-submitted."""

    def post(self, request, pk, provider):
        app = get_object_or_404(MobileApplication, pk=pk)
        require_manageable_project(request.user, app.project_id)
        store_app = service.ensure_store_application(app, provider)
        assets = service.generate_store_screenshots(store_app, user=request.user)
        return Response(
            {"screenshots": [_asset_dict(a) for a in assets]},
            status=status.HTTP_201_CREATED,
        )


class StoreScreenshotsApproveView(APIView):
    def post(self, request, pk, provider):
        app = get_object_or_404(MobileApplication, pk=pk)
        require_manageable_project(request.user, app.project_id)
        store_app = app.store_apps.filter(provider=provider).first()
        if store_app is None:
            return Response(
                {"detail": "Generate screenshots before approving them."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        n = service.approve_screenshots(store_app, user=request.user)
        return Response({"approved": n})


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
