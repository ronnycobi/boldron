"""Recurring billing / subscriptions (spec §24) — on the real commerce spine.

A subscription's money is deterministic: a fixed plan amount every interval. Each
billing cycle is settled through a GENUINE Order (so it is payable, refundable and
invoiceable exactly like any other order) — nothing fakes a charge or a "paid"
status. Card auto-renewal is gated on a connected gateway; until then every cycle
is a manual payment the merchant confirms, which is real and offline-honest.

The renewal engine (`renew_due`) is deterministic and idempotent: it opens the next
cycle's order only when the current period has ended and no cycle order is still
outstanding, so running it repeatedly never double-bills.
"""
from __future__ import annotations

import calendar
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.service import record as audit
from apps.publishing import ecommerce_service as shop
from apps.publishing.models import (
    Order, OrderItem, Subscription, SubscriptionInvoice, SubscriptionPlan,
)


class SubscriptionError(Exception):
    pass


def _advance(dt, interval: str):
    if interval == "weekly":
        return dt + timedelta(days=7)
    if interval == "yearly":
        try:
            return dt.replace(year=dt.year + 1)
        except ValueError:          # Feb 29 → Feb 28
            return dt.replace(year=dt.year + 1, day=28)
    # monthly (default): add one calendar month, clamping the day.
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def create_plan(website, *, name, amount_cents, interval="monthly", currency="USD",
                user=None) -> SubscriptionPlan:
    name = (name or "").strip()
    if not name:
        raise SubscriptionError("A plan needs a name.")
    if int(amount_cents) <= 0:
        raise SubscriptionError("A plan amount must be greater than zero.")
    if interval not in dict(SubscriptionPlan.INTERVALS):
        raise SubscriptionError(f"Unknown interval '{interval}'.")
    plan = SubscriptionPlan.objects.create(
        website=website, name=name, amount_cents=int(amount_cents),
        currency=(currency or "USD").upper()[:3], interval=interval,
    )
    audit("subscription.plan", actor=user, organization=website.project.organization,
          target=f"plan:{plan.id}", summary=f"{plan.name} {plan.amount_display}/{plan.interval}")
    return plan


def _open_cycle(subscription: Subscription, *, period_start, period_end,
                provider_key="manual") -> Order:
    """Open a real billing cycle: a manual Order for the plan amount (+ the store's
    active tax), with a pending payment. The order IS the bill for this cycle."""
    plan = subscription.plan
    website = subscription.website
    with transaction.atomic():
        order = Order.objects.create(
            website=website, reference=shop._reference(), channel="web",
            customer_name=subscription.customer_name, customer_email=subscription.customer_email,
            currency=plan.currency, status="pending",
        )
        label = f"{plan.name} — {plan.get_interval_display().lower()} subscription"
        OrderItem.objects.create(order=order, product=None, name=label,
                                 unit_price_cents=plan.amount_cents, quantity=1)
        subtotal = plan.amount_cents
        tax_rate = website.tax_rates.filter(active=True).first()
        tax = tax_rate.tax_for(subtotal) if tax_rate else 0
        order.subtotal_cents = subtotal
        order.tax_cents = tax
        order.tax_rate = tax_rate
        order.total_cents = subtotal + tax
        order.save(update_fields=["subtotal_cents", "tax_cents", "tax_rate",
                                  "total_cents", "updated_at"])
        SubscriptionInvoice.objects.create(
            subscription=subscription, order=order,
            period_start=period_start, period_end=period_end)
    # Create the pending payment + buyer confirmation via the real checkout path.
    shop.start_checkout(order, provider_key=provider_key)
    return order


def subscribe(plan: SubscriptionPlan, *, customer_name="", customer_email="",
              user=None, now=None) -> tuple[Subscription, Order]:
    """Start a subscription and open its first billing cycle (an unpaid Order due now)."""
    if not plan.active:
        raise SubscriptionError("That plan is no longer offered.")
    now = now or timezone.now()
    period_end = _advance(now, plan.interval)
    subscription = Subscription.objects.create(
        website=plan.website, plan=plan,
        customer_name=(customer_name or "").strip(),
        customer_email=(customer_email or "").strip(),
        status="active", current_period_start=now, current_period_end=period_end,
    )
    order = _open_cycle(subscription, period_start=now, period_end=period_end)
    audit("subscription.start", actor=user, organization=plan.website.project.organization,
          target=f"subscription:{subscription.id}", summary=plan.name)
    return subscription, order


def _outstanding_cycle(subscription: Subscription) -> SubscriptionInvoice | None:
    """A cycle whose order hasn't been paid (and wasn't cancelled/refunded)."""
    return (subscription.cycles.select_related("order")
            .exclude(order__status__in=("paid", "refunded", "cancelled"))
            .order_by("-created_at").first())


def settle_cycle(order: Order, *, user) -> Subscription:
    """Merchant confirms the cycle's manual payment (real money received). The
    subscription returns to active and the settled-cycle count increments."""
    cycle = getattr(order, "subscription_cycle", None)
    if cycle is None:
        raise SubscriptionError("That order is not a subscription cycle.")
    shop.confirm_manual_payment(order, user=user)
    sub = cycle.subscription
    if sub.status != "cancelled":
        sub.status = "active"
    sub.renewals = sub.cycles.filter(order__status="paid").count()
    sub.save(update_fields=["status", "renewals"])
    return sub


def renew_due(*, now=None, website=None) -> int:
    """Open the next cycle for every subscription whose period has ended and has no
    outstanding cycle order. Deterministic + idempotent — safe to run repeatedly."""
    now = now or timezone.now()
    qs = Subscription.objects.filter(
        status__in=("active", "past_due"), current_period_end__lte=now)
    if website is not None:
        qs = qs.filter(website=website)
    opened = 0
    for sub in qs.select_related("plan", "website"):
        if _outstanding_cycle(sub) is not None:
            continue  # last cycle still unpaid — don't stack another bill
        period_start = sub.current_period_end
        period_end = _advance(period_start, sub.plan.interval)
        _open_cycle(sub, period_start=period_start, period_end=period_end)
        sub.current_period_start = period_start
        sub.current_period_end = period_end
        sub.status = "past_due"   # honest: the new cycle is unpaid until settled
        sub.save(update_fields=["current_period_start", "current_period_end", "status"])
        opened += 1
    return opened


def cancel(subscription: Subscription, *, user=None) -> Subscription:
    """Cancel a subscription: no further cycles are opened. Any already-open unpaid
    cycle order stays as-is (the merchant can cancel that order separately)."""
    subscription.status = "cancelled"
    subscription.cancelled_at = timezone.now()
    subscription.save(update_fields=["status", "cancelled_at"])
    audit("subscription.cancel", actor=user,
          organization=subscription.website.project.organization,
          target=f"subscription:{subscription.id}", summary=subscription.plan.name)
    return subscription


def overview(website) -> dict:
    """A real subscriptions summary for a store — counts and recurring revenue from
    actual records, nothing fabricated."""
    subs = list(website.subscriptions.select_related("plan"))
    active = [s for s in subs if s.status in ("active", "past_due")]
    # Normalise each active plan's amount to a monthly figure for MRR.
    factor = {"weekly": 52 / 12, "monthly": 1, "yearly": 1 / 12}
    mrr = sum(round(s.plan.amount_cents * factor[s.plan.interval]) for s in active)
    currency = subs[0].plan.currency if subs else "USD"
    return {
        "plans": website.plans.filter(active=True).count(),
        "total": len(subs),
        "active": len(active),
        "past_due": sum(1 for s in subs if s.status == "past_due"),
        "cancelled": sum(1 for s in subs if s.status == "cancelled"),
        "mrr_cents": mrr,
        "mrr_display": f"{currency} {mrr / 100:.2f}",
    }
