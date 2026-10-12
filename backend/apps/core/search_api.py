"""Global search API (mobile/API client) — spec §28.

Searches the entities the signed-in user can actually see, scoped to their
organizations: projects, products, orders, support tickets and mobile apps.
Real queries against the shared models — never a separate search index that
could drift from the source of truth.
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.access import organizations_for

_LIMIT = 10  # results per category


class GlobalSearchView(APIView):
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"query": "", "results": {}})

        orgs = organizations_for(request.user)
        results = {
            "projects": self._projects(orgs, q),
            "products": self._products(orgs, q),
            "orders": self._orders(orgs, q),
            "tickets": self._tickets(orgs, q),
            "mobile_apps": self._mobile_apps(orgs, q),
        }
        return Response({"query": q, "results": results})

    def _projects(self, orgs, q):
        from apps.projects.models import Project

        rows = Project.objects.filter(organization__in=orgs, name__icontains=q)[:_LIMIT]
        return [{"id": p.id, "name": p.name, "organization": p.organization_id} for p in rows]

    def _products(self, orgs, q):
        from apps.publishing.models import Product

        rows = Product.objects.filter(
            website__project__organization__in=orgs, name__icontains=q
        ).select_related("website")[:_LIMIT]
        return [
            {"id": p.id, "name": p.name, "project": p.website.project_id,
             "price_display": p.price_display}
            for p in rows
        ]

    def _orders(self, orgs, q):
        from django.db.models import Q

        from apps.publishing.models import Order

        rows = Order.objects.filter(
            Q(website__project__organization__in=orgs)
            & (Q(reference__icontains=q) | Q(customer_name__icontains=q)
               | Q(customer_email__icontains=q))
        ).select_related("website")[:_LIMIT]
        return [
            {"id": o.id, "reference": o.reference, "status": o.status,
             "total_display": o.total_display, "project": o.website.project_id}
            for o in rows
        ]

    def _tickets(self, orgs, q):
        from apps.support.models import SupportTicket

        rows = SupportTicket.objects.filter(organization__in=orgs, subject__icontains=q)[:_LIMIT]
        return [{"id": t.id, "number": t.number, "subject": t.subject, "status": t.status}
                for t in rows]

    def _mobile_apps(self, orgs, q):
        from apps.release.models import MobileApplication

        rows = MobileApplication.objects.filter(
            project__organization__in=orgs, name__icontains=q
        )[:_LIMIT]
        return [{"id": a.id, "name": a.name, "project": a.project_id} for a in rows]
