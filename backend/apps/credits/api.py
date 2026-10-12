from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.credits.models import Invoice, UsageRecord
from apps.credits.services import get_account
from apps.organizations.access import manageable_organizations_for, organizations_for
from apps.organizations.models import Organization


def _member_org(user, org_pk):
    return get_object_or_404(organizations_for(user), pk=org_pk)


def _decimals_to_str(d: dict) -> dict:
    """Render Decimal values as strings (JSON has no native decimal)."""
    return {k: (str(v) if hasattr(v, "quantize") else v) for k, v in d.items()}


class CreditBalanceView(APIView):
    """The org's credit balance. No account => unlimited (development default)."""

    def get(self, request, org_pk):
        org = _member_org(request.user, org_pk)
        account = get_account(org)
        if account is None:
            return Response(
                {"organization": org.id, "unlimited": True, "plan": None, "balance": None}
            )
        return Response(
            {
                "organization": org.id,
                "unlimited": False,
                "plan": account.plan,
                "balance": str(account.balance),
            }
        )


class UsageListView(APIView):
    """Recent usage records for the org (most recent first)."""

    def get(self, request, org_pk):
        org = _member_org(request.user, org_pk)
        records = UsageRecord.objects.filter(organization=org)[:100]
        return Response(
            [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat(),
                    "agent_key": r.agent_key,
                    "provider": r.provider,
                    "model": r.model,
                    "total_tokens": r.total_tokens,
                    "cost_usd": str(r.cost_usd),
                    "credits_charged": str(r.credits_charged),
                    "project": r.project_id,
                    "task": r.task_id,
                }
                for r in records
            ]
        )


class BillingView(APIView):
    """Consolidated billing snapshot for an org: plan, balance vs allowance,
    this month's spend, daily cap, and the upgrade options. Honest — it shows
    real credit/usage data only; there is no fabricated payment method or
    transaction history (live billing needs a payment provider, not yet
    connected)."""

    def get(self, request, org_pk):
        from apps.credits.catalog import billing_summary

        org = _member_org(request.user, org_pk)
        summary = billing_summary(org)
        summary["can_manage"] = manageable_organizations_for(request.user).filter(pk=org.id).exists()
        upgrades = summary.pop("upgrades")
        return Response({**_decimals_to_str(summary), "upgrades": upgrades})


class UsageSummaryView(APIView):
    """Usage aggregates for an org: totals this month and a breakdown by model.
    Lighter than the full record list, for a usage dashboard."""

    def get(self, request, org_pk):
        from django.db.models import Sum
        from django.utils import timezone as tz

        org = _member_org(request.user, org_pk)
        month_start = tz.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        qs = UsageRecord.objects.filter(organization=org, created_at__gte=month_start)
        total = qs.aggregate(
            cost=Sum("cost_usd"), credits=Sum("credits_charged"), tokens=Sum("total_tokens")
        )
        by_model = [
            {
                "model": row["model"] or "—",
                "tokens": row["tokens"] or 0,
                "cost_usd": str(row["cost"] or 0),
                "credits": str(row["credits"] or 0),
            }
            for row in qs.values("model")
            .annotate(cost=Sum("cost_usd"), credits=Sum("credits_charged"), tokens=Sum("total_tokens"))
            .order_by("-cost")
        ]
        return Response(
            {
                "organization": org.id,
                "period_start": month_start.date().isoformat(),
                "total_cost_usd": str(total["cost"] or 0),
                "total_credits": str(total["credits"] or 0),
                "total_tokens": total["tokens"] or 0,
                "by_model": by_model,
            }
        )


class InvoiceListView(APIView):
    """Billing history: the org's invoices, most recent first (real records)."""

    def get(self, request, org_pk):
        org = _member_org(request.user, org_pk)
        invoices = Invoice.objects.filter(organization=org).order_by("-period_start")
        return Response(
            [
                {
                    "id": inv.id,
                    "period_start": inv.period_start.isoformat(),
                    "period_end": inv.period_end.isoformat(),
                    "currency": inv.currency,
                    "subtotal_usd": str(inv.subtotal_usd),
                    "credits_used": str(inv.credits_used),
                    "status": inv.status,
                    "lines": inv.lines,
                    "created_at": inv.created_at.isoformat(),
                }
                for inv in invoices
            ]
        )


class UpgradeRequestView(APIView):
    """Request a plan upgrade. With no live billing connected, this opens a
    billing support ticket (identical to the web flow) rather than charging a
    card — honest about what actually happens."""

    def post(self, request, org_pk):
        from apps.credits.catalog import PLAN_LABEL
        from apps.support.service import create_ticket

        org = _member_org(request.user, org_pk)
        if not manageable_organizations_for(request.user).filter(pk=org.id).exists():
            return Response(
                {"detail": "Owner or admin rights required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        target = (request.data.get("plan") or "").strip()
        label = PLAN_LABEL.get(target, target or "a higher")
        ticket = create_ticket(
            organization=org, user=request.user, category="billing", priority="normal",
            subject=f"Upgrade request — {label} plan",
            body=f"{request.user.email} requested upgrading “{org.name}” to the {label} plan.",
        )
        return Response(
            {
                "detail": "Upgrade request sent — our team will follow up. "
                          "Track it under Support.",
                "ticket_number": ticket.number,
            },
            status=status.HTTP_201_CREATED,
        )
