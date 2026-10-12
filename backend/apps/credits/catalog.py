"""Plan presentation + per-org billing summary.

The credit *plans* (allowances) are defined in services.plans(); this module adds
the customer-facing presentation (label, price, features, order) and assembles the
billing summary shown on the web Settings hub and the mobile billing screen, so
both read the same source. Prices/features mirror the public pricing — honest, no
fabricated billing.
"""
from __future__ import annotations

from decimal import Decimal

PLAN_ORDER = ["free", "pro", "business", "enterprise"]
PLAN_LABEL = {"free": "Free", "pro": "Builder", "business": "Business", "enterprise": "Enterprise"}
PLAN_PRICE = {"free": "$0", "pro": "$29/mo", "business": "$99/mo", "enterprise": "Custom"}
PLAN_FEATURES = {
    "free": ["Build websites & web apps", "Live preview", "Export your code anytime",
             "1 published project", "Community support"],
    "pro": ["Everything in Free", "5× the monthly AI credits", "Deploy to dev & staging",
            "Git integration", "Custom domains", "Email support"],
    "business": ["Everything in Builder", "Team collaboration & roles",
                 "Mobile app-store releases", "Monitoring & audit logs", "Priority support"],
    "enterprise": ["Everything in Business", "SSO & advanced controls",
                   "Private deployments", "Dedicated support & SLA"],
}


def plan_presentation(plan: str) -> dict:
    return {
        "plan": plan,
        "label": PLAN_LABEL.get(plan, plan.title()),
        "price": PLAN_PRICE.get(plan, ""),
        "features": PLAN_FEATURES.get(plan, []),
    }


def upgrade_options(plan: str) -> list[dict]:
    """Plans above the current one (empty for the top tier / unknown plan)."""
    if plan not in PLAN_ORDER:
        return []
    return [plan_presentation(p) for p in PLAN_ORDER[PLAN_ORDER.index(plan) + 1:]]


def billing_summary(organization) -> dict:
    """The full billing snapshot for one organization: plan, balance vs
    allowance, this month's spend, daily cap, and upgrade options. Decimals are
    returned as-is; API serializers stringify them."""
    from django.db.models import Sum
    from django.utils import timezone as tz

    from apps.credits.models import UsageRecord
    from apps.credits.services import daily_usd_cap, get_account, plans

    acct = get_account(organization)
    plan = acct.plan if acct else "free"
    allowance = Decimal(str(plans().get(plan, 0)))
    balance = acct.balance if acct else Decimal("0")
    remaining_pct = int(min(balance, allowance) / allowance * 100) if allowance else 0

    month_start = tz.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = UsageRecord.objects.filter(
        organization=organization, created_at__gte=month_start
    ).aggregate(spend=Sum("cost_usd"), credits=Sum("credits_charged"), tokens=Sum("total_tokens"))

    return {
        "organization": organization.id,
        "has_account": acct is not None,
        **plan_presentation(plan),
        "allowance": allowance,
        "balance": balance,
        "remaining_pct": remaining_pct,
        "low": remaining_pct < 15,
        "daily_cap": daily_usd_cap(acct) if acct else None,
        "month_spend": month["spend"] or Decimal("0"),
        "month_credits": month["credits"] or Decimal("0"),
        "month_tokens": month["tokens"] or 0,
        "upgrades": upgrade_options(plan),
    }
