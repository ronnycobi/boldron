"""Website management API (mobile/API client).

The authenticated website-management surface over apps.publishing: status,
publish/versions/rollback, custom domains, forms & leads. Every mutation goes
through the existing publishing services, so web and mobile manage the same
sites and see the same state. Custom-domain verification and SSL stay honest —
a domain is 'verified'/'live' only when a real DNS/certificate check says so;
nothing here fakes it.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.access import project_for_read, require_manageable_project
from apps.publishing import domain_service, service
from apps.publishing.models import CustomDomain, Website


def _website(project):
    return getattr(project, "website", None)


def _version_dict(v) -> dict:
    return {
        "id": v.id,
        "version": v.version,
        "environment": v.environment,
        "state": v.state,
        "url": v.url,
        "health": v.health,
        "readiness": v.readiness,
        "is_current": v.is_current,
        "created_at": v.created_at.isoformat(),
    }


def _domain_dict(d: CustomDomain) -> dict:
    return {
        "id": d.id,
        "hostname": d.hostname,
        "verification_status": d.verification_status,
        "ssl_status": d.ssl_status,
        "is_verified": d.is_verified,
        "is_live": d.is_live,
        "required_records": d.required_records,
        "detail": d.detail,
        "created_at": d.created_at.isoformat(),
    }


def _website_dict(w: Website) -> dict:
    current = w.current
    return {
        "id": w.id,
        "project": w.project_id,
        "subdomain": w.subdomain,
        "site_type": w.site_type,
        "current_version": _version_dict(current) if current else None,
        "url": current.url if current else "",
        "domains": [_domain_dict(d) for d in w.domains.all()],
    }


class _SiteView(APIView):
    manage = False

    def site(self, request, project_pk):
        if self.manage:
            project = require_manageable_project(request.user, project_pk)
        else:
            project = project_for_read(request.user, project_pk)
        website = _website(project)
        if website is None:
            from django.http import Http404

            raise Http404("This project does not have a website.")
        return website


class WebsiteView(_SiteView):
    def get(self, request, project_pk):
        return Response(_website_dict(self.site(request, project_pk)))


class PublishView(_SiteView):
    manage = True

    def post(self, request, project_pk):
        website = self.site(request, project_pk)
        try:
            version = service.publish(website, user=request.user)
        except service.PublishError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_version_dict(version), status=status.HTTP_201_CREATED)


class VersionListView(_SiteView):
    def get(self, request, project_pk):
        website = self.site(request, project_pk)
        return Response([_version_dict(v) for v in website.versions.all()])


class RollbackView(_SiteView):
    manage = True

    def post(self, request, project_pk):
        website = self.site(request, project_pk)
        try:
            version = service.rollback(website, user=request.user)
        except service.PublishError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_version_dict(version))


class DomainListCreateView(_SiteView):
    def get(self, request, project_pk):
        website = self.site(request, project_pk)
        return Response([_domain_dict(d) for d in website.domains.all()])

    def post(self, request, project_pk):
        self.manage = True
        website = self.site(request, project_pk)
        try:
            domain = domain_service.connect_domain(
                website, hostname=(request.data.get("hostname") or "").strip(),
                user=request.user,
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_domain_dict(domain), status=status.HTTP_201_CREATED)


class _DomainActionView(APIView):
    def domain(self, request, pk, *, manage=True):
        domain = get_object_or_404(CustomDomain, pk=pk)
        if manage:
            require_manageable_project(request.user, domain.website.project_id)
        else:
            project_for_read(request.user, domain.website.project_id)
        return domain


class DomainVerifyView(_DomainActionView):
    def post(self, request, pk):
        domain = self.domain(request, pk)
        domain_service.verify_domain(domain, user=request.user)
        return Response(_domain_dict(domain))


class DomainSslView(_DomainActionView):
    def post(self, request, pk):
        domain = self.domain(request, pk)
        try:
            domain_service.request_ssl(domain, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_domain_dict(domain))


class DomainRemoveView(_DomainActionView):
    def delete(self, request, pk):
        domain = self.domain(request, pk)
        domain_service.remove_domain(domain, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MonitoringView(_SiteView):
    """Site health: an uptime summary plus the latest probe. GET reads; POST runs
    a fresh probe. Honest scope — this checks the snapshot the platform actually
    serves (present/readable + serve latency), never remote server metrics it
    can't see."""

    def get(self, request, project_pk):
        from apps.publishing import monitor

        website = self.site(request, project_pk)
        latest = website.health_checks.first()
        return Response(
            {
                "project": website.project_id,
                "uptime": monitor.uptime_summary(website),
                "latest": None
                if latest is None
                else {
                    "status": latest.status,
                    "detail": latest.detail,
                    "response_ms": latest.response_ms,
                    "checked_at": latest.checked_at.isoformat(),
                },
            }
        )

    def post(self, request, project_pk):
        from apps.publishing import monitor

        self.manage = True
        website = self.site(request, project_pk)
        check = monitor.run_check(website)
        if check is None:
            return Response(
                {"detail": "Nothing is published yet to monitor."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "status": check.status,
                "detail": check.detail,
                "response_ms": check.response_ms,
                "checked_at": check.checked_at.isoformat(),
            }
        )


class AnalyticsView(_SiteView):
    """Visitor analytics for the published site (privacy-preserving, real data).
    ?days=N (default 30, max 365)."""

    def get(self, request, project_pk):
        from apps.publishing import analytics

        website = self.site(request, project_pk)
        try:
            days = min(365, max(1, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30
        return Response(analytics.summary(website, days=days))


class FormLeadListView(_SiteView):
    """The site's captured leads (form submissions), newest first — read-only."""

    def get(self, request, project_pk):
        website = self.site(request, project_pk)
        from apps.publishing.models import Lead

        leads = Lead.objects.filter(website=website).order_by("-created_at")[:200]
        return Response(
            [
                {
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "message": lead.message,
                    "status": lead.status,
                    "created_at": lead.created_at.isoformat(),
                }
                for lead in leads
            ]
        )
