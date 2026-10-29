"""Merchant commerce admin API (mobile/API client).

The authenticated store-management side of the SHARED commerce engine
(apps.publishing.ecommerce_service + models). Web, Android and iOS all drive the
same engine and the same data — a product edited or an order refunded here is
immediately reflected on web, and vice-versa. No commerce logic is duplicated:
every mutation goes through ecommerce_service, which owns pricing, inventory,
discounts and refunds.

The public storefront (shopper) endpoints live in api.py; this module is the
merchant console: it requires org membership, and owner/admin for writes.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.access import project_for_read, require_manageable_project
from apps.publishing import ecommerce_service as shop
from apps.publishing import subscriptions as subs
from apps.publishing.models import DiscountCode, Order, Product


def _website(project):
    """The project's store, or None if it isn't a commerce project yet."""
    return getattr(project, "website", None)


def _product_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "name": p.name,
        "description": p.description,
        "price_cents": p.price_cents,
        "price_display": p.price_display,
        "currency": p.currency,
        "active": p.active,
        "track_inventory": p.track_inventory,
        "stock": p.stock,
        "in_stock": p.in_stock,
        "has_variants": p.has_variants,
        "variants": [_variant_dict(v) for v in p.variants.all()],
    }


def _variant_dict(v) -> dict:
    return {
        "id": v.id,
        "label": v.label,
        "options": v.options,
        "sku": v.sku,
        "price_cents": v.price_cents,
        "track_inventory": v.track_inventory,
        "stock": v.stock,
        "active": v.active,
        "in_stock": v.in_stock,
    }


def _order_dict(o: Order, *, items=False) -> dict:
    data = {
        "id": o.id,
        "reference": o.reference,
        "channel": o.channel,
        "status": o.status,
        "customer_name": o.customer_name,
        "customer_email": o.customer_email,
        "currency": o.currency,
        "subtotal_cents": o.subtotal_cents,
        "discount_cents": o.discount_cents,
        "tax_cents": o.tax_cents,
        "shipping_cents": o.shipping_cents,
        "total_cents": o.total_cents,
        "total_display": o.total_display,
        "created_at": o.created_at.isoformat(),
    }
    if items:
        data["items"] = [
            {
                "name": it.name,
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "line_total_cents": it.line_total_cents,
                "product": it.product_id,
                "variant": it.variant_id,
            }
            for it in o.items.all()
        ]
        data["shipping_address"] = o.shipping_address
    return data


def _discount_dict(d: DiscountCode) -> dict:
    return {
        "id": d.id,
        "code": d.code,
        "kind": d.kind,
        "percent_off": d.percent_off,
        "amount_off_cents": d.amount_off_cents,
        "currency": d.currency,
        "min_subtotal_cents": d.min_subtotal_cents,
        "max_uses": d.max_uses,
    }


class _StoreView(APIView):
    """Base: resolve the project's store, 404 when the project has no store yet."""

    manage = False

    def store(self, request, project_pk):
        if self.manage:
            project = require_manageable_project(request.user, project_pk)
        else:
            project = project_for_read(request.user, project_pk)
        website = _website(project)
        if website is None:
            from django.http import Http404

            raise Http404("This project does not have a store.")
        return website


# --- Products ---------------------------------------------------------------

class ProductListCreateView(_StoreView):
    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        products = website.products.all().prefetch_related("variants")
        return Response([_product_dict(p) for p in products])

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        try:
            product = shop.create_product(
                website,
                name=(request.data.get("name") or "").strip(),
                price_cents=int(request.data.get("price_cents") or 0),
                currency=request.data.get("currency") or "USD",
                description=request.data.get("description") or "",
                track_inventory=bool(request.data.get("track_inventory")),
                stock=int(request.data.get("stock") or 0),
                user=request.user,
            )
        except (shop.EcommerceError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_product_dict(product), status=status.HTTP_201_CREATED)


class ProductDetailView(_StoreView):
    _EDITABLE = {"name", "description", "price_cents", "currency", "active",
                 "track_inventory", "stock"}

    def _product(self, website, pk):
        return get_object_or_404(Product, pk=pk, website=website)

    def get(self, request, project_pk, pk):
        self.manage = False
        website = self.store(request, project_pk)
        return Response(_product_dict(self._product(website, pk)))

    def patch(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        product = self._product(website, pk)
        changed = []
        for field in self._EDITABLE:
            if field in request.data:
                value = request.data[field]
                if field in {"price_cents", "stock"}:
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        return Response(
                            {field: ["Must be a whole number."]},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if field == "price_cents" and value < 0:
                        return Response(
                            {field: ["Price cannot be negative."]},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                elif field in {"active", "track_inventory"}:
                    value = bool(value)
                setattr(product, field, value)
                changed.append(field)
        if changed:
            product.save(update_fields=changed)
        return Response(_product_dict(product))

    def delete(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        self._product(website, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VariantListCreateView(_StoreView):
    def post(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        product = get_object_or_404(Product, pk=pk, website=website)
        try:
            variant = shop.create_variant(
                product,
                label=(request.data.get("label") or "").strip(),
                price_cents=int(request.data.get("price_cents") or 0),
                options=request.data.get("options") or {},
                sku=request.data.get("sku") or "",
                track_inventory=bool(request.data.get("track_inventory", True)),
                stock=int(request.data.get("stock") or 0),
                user=request.user,
            )
        except (shop.EcommerceError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_variant_dict(variant), status=status.HTTP_201_CREATED)


# --- Inventory --------------------------------------------------------------

class InventoryView(_StoreView):
    """Stock levels (GET) and a stock adjustment (POST: delta or absolute)."""

    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        from apps.publishing.models import ProductVariant

        rows = []
        for p in website.products.filter(track_inventory=True):
            rows.append({"type": "product", "id": p.id, "name": p.name, "stock": p.stock,
                         "low": p.stock <= 5})
        for v in ProductVariant.objects.filter(product__website=website, track_inventory=True):
            rows.append({"type": "variant", "id": v.id, "name": str(v), "stock": v.stock,
                         "low": v.stock <= 5})
        return Response({"items": rows})

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        kind = request.data.get("type")
        obj_id = request.data.get("id")
        from apps.publishing.models import ProductVariant

        model = {"product": Product, "variant": ProductVariant}.get(kind)
        if model is None:
            return Response({"type": ["Must be 'product' or 'variant'."]},
                            status=status.HTTP_400_BAD_REQUEST)
        if model is Product:
            obj = get_object_or_404(Product, pk=obj_id, website=website)
        else:
            obj = get_object_or_404(ProductVariant, pk=obj_id, product__website=website)
        if "stock" in request.data:
            obj.stock = int(request.data["stock"])
        elif "delta" in request.data:
            obj.stock = obj.stock + int(request.data["delta"])
        else:
            return Response({"detail": "Provide 'stock' (absolute) or 'delta' (change)."},
                            status=status.HTTP_400_BAD_REQUEST)
        obj.stock = max(0, obj.stock)
        obj.save(update_fields=["stock"])
        return Response({"type": kind, "id": obj.id, "stock": obj.stock})


# --- Orders -----------------------------------------------------------------

class OrderListView(_StoreView):
    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        orders = website.orders.all()
        state = request.query_params.get("status")
        if state:
            orders = orders.filter(status=state)
        return Response([_order_dict(o) for o in orders[:200]])


class OrderDetailView(_StoreView):
    def get(self, request, project_pk, pk):
        self.manage = False
        website = self.store(request, project_pk)
        order = get_object_or_404(Order, pk=pk, website=website)
        return Response(_order_dict(order, items=True))


class OrderRefundView(_StoreView):
    def post(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        order = get_object_or_404(Order, pk=pk, website=website)
        try:
            shop.refund_order(order, user=request.user, reason=request.data.get("reason", ""))
        except shop.EcommerceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_order_dict(order, items=True))


class OrderCancelView(_StoreView):
    def post(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        order = get_object_or_404(Order, pk=pk, website=website)
        try:
            shop.cancel_order(order, user=request.user)
        except shop.EcommerceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_order_dict(order, items=True))


# --- Discounts --------------------------------------------------------------

class DiscountListCreateView(_StoreView):
    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        return Response([_discount_dict(d) for d in website.discount_codes.all()])

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        try:
            dc = shop.create_discount(
                website,
                code=request.data.get("code", ""),
                kind=request.data.get("kind", "percent"),
                percent_off=int(request.data.get("percent_off") or 0),
                amount_off_cents=int(request.data.get("amount_off_cents") or 0),
                currency=request.data.get("currency") or "USD",
                min_subtotal_cents=int(request.data.get("min_subtotal_cents") or 0),
                max_uses=int(request.data.get("max_uses") or 0),
                user=request.user,
            )
        except (shop.EcommerceError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_discount_dict(dc), status=status.HTTP_201_CREATED)


# --- Sales ------------------------------------------------------------------

class SalesSummaryView(_StoreView):
    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        return Response(shop.sales_summary(website))


class OrderInvoiceView(_StoreView):
    """The invoice for one of this store's orders, as structured data (spec §24/§32).
    Built from the real order + payments — the same engine the web console renders."""

    def get(self, request, project_pk, pk):
        from apps.publishing import invoicing
        self.manage = False
        website = self.store(request, project_pk)
        order = get_object_or_404(
            Order.objects.prefetch_related("items", "payments"), pk=pk, website=website)
        return Response(invoicing.invoice_data(order))


class TaxRateView(_StoreView):
    """GET the store's active tax rate; POST sets it (owner/admin). Real, deterministic
    VAT/sales-tax applied at checkout and itemised on invoices."""

    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        rate = website.tax_rates.filter(active=True).first()
        if rate is None:
            return Response({"name": None, "percent": None, "rate_display": None})
        return Response({"name": rate.name, "rate_bps": rate.rate_bps,
                         "percent": rate.rate_bps / 100, "rate_display": rate.rate_display})

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        try:
            rate = shop.set_tax_rate(
                website, name=request.data.get("name", "Tax"),
                percent=request.data.get("percent", 0), user=request.user)
        except shop.EcommerceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"name": rate.name, "rate_display": rate.rate_display},
                        status=status.HTTP_201_CREATED)


# --- Subscriptions (recurring billing) --------------------------------------

def _plan_dict(p) -> dict:
    return {
        "id": p.id, "name": p.name, "amount_cents": p.amount_cents,
        "amount_display": p.amount_display, "currency": p.currency,
        "interval": p.interval, "active": p.active,
    }


def _subscription_dict(s) -> dict:
    return {
        "id": s.id, "plan": s.plan_name, "plan_id": s.plan_id,
        "customer_name": s.customer_name, "customer_email": s.customer_email,
        "status": s.status, "renewals": s.renewals,
        "current_period_end": s.current_period_end.isoformat(),
        "amount_display": s.amount_display, "interval": s.interval,
    }


class PlanListCreateView(_StoreView):
    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        return Response([_plan_dict(p) for p in website.plans.all()])

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        d = request.data
        try:
            plan = subs.create_plan(
                website, name=d.get("name", ""), amount_cents=d.get("amount_cents", 0),
                interval=d.get("interval", "monthly"), currency=d.get("currency", "USD"),
                user=request.user)
        except subs.SubscriptionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_plan_dict(plan), status=status.HTTP_201_CREATED)


class SubscriptionListCreateView(_StoreView):
    """GET lists a store's subscriptions; POST subscribes a customer to a plan and
    opens the first (real, unpaid) billing cycle."""

    def get(self, request, project_pk):
        self.manage = False
        website = self.store(request, project_pk)
        return Response({
            "overview": subs.overview(website),
            "subscriptions": [_subscription_dict(s)
                              for s in website.subscriptions.select_related("plan")[:200]],
        })

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        plan = website.plans.filter(pk=request.data.get("plan_id"), active=True).first()
        if plan is None:
            return Response({"detail": "Unknown or inactive plan."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            sub, order = subs.subscribe(
                plan, customer_name=request.data.get("customer_name", ""),
                customer_email=request.data.get("customer_email", ""), user=request.user)
        except subs.SubscriptionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"subscription": _subscription_dict(sub),
                         "first_cycle_order": order.reference},
                        status=status.HTTP_201_CREATED)


class SubscriptionCancelView(_StoreView):
    def post(self, request, project_pk, pk):
        self.manage = True
        website = self.store(request, project_pk)
        sub = get_object_or_404(website.subscriptions, pk=pk)
        subs.cancel(sub, user=request.user)
        return Response(_subscription_dict(sub))


class SubscriptionRenewView(_StoreView):
    """Open any due billing cycles for this store now (the same work the scheduled
    command does). Returns how many real cycle orders were opened."""

    def post(self, request, project_pk):
        self.manage = True
        website = self.store(request, project_pk)
        opened = subs.renew_due(website=website)
        return Response({"opened": opened})


# --- Multi-currency ---------------------------------------------------------

class CurrencyView(_StoreView):
    """Supported currencies, the store's stored exchange rates, and the honest live-
    feed status. POST stores a real exchange rate (owner/admin)."""

    def get(self, request, project_pk):
        from apps.publishing import currency
        self.manage = False
        website = self.store(request, project_pk)
        org = website.project.organization
        rates = [{"base": r.base_code, "quote": r.quote_code,
                  "rate": str(r.rate), "source": r.source,
                  "updated_at": r.updated_at.isoformat()}
                 for r in org.currency_rates.all()]
        return Response({
            "supported": currency.supported_currencies(),
            "rates": rates,
            "live_feed": currency.live_feed_status(),
        })

    def post(self, request, project_pk):
        from apps.publishing import currency
        self.manage = True
        website = self.store(request, project_pk)
        d = request.data
        try:
            currency.set_rate(website.project.organization,
                              base=d.get("base", ""), quote=d.get("quote", ""),
                              rate=d.get("rate", 0), user=request.user)
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_201_CREATED)


class CurrencyRevenueView(_StoreView):
    """Real paid revenue grouped by the currency it was charged in; optionally
    converted to a ?base= currency using stored rates (unconvertible buckets flagged)."""

    def get(self, request, project_pk):
        from apps.publishing import currency
        self.manage = False
        website = self.store(request, project_pk)
        base = request.query_params.get("base")
        base = currency.normalise(base) if base else None
        return Response(currency.revenue_by_currency(website, base=base))


# --- Email campaigns --------------------------------------------------------

def _campaign_dict(c) -> dict:
    return {
        "id": c.id, "subject": c.subject, "audience_source": c.audience_source,
        "status": c.status, "total": c.total, "sent_count": c.sent_count,
        "failed_count": c.failed_count, "created_at": c.created_at.isoformat(),
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
    }


class CampaignListCreateView(_StoreView):
    def get(self, request, project_pk):
        from apps.publishing import campaigns
        self.manage = False
        website = self.store(request, project_pk)
        audience = campaigns.build_audience(website, request.query_params.get("audience", "all"))
        return Response({
            "audience_size": len(audience),
            "campaigns": [_campaign_dict(c) for c in website.campaigns.all()[:100]],
        })

    def post(self, request, project_pk):
        from apps.publishing import campaigns
        self.manage = True
        website = self.store(request, project_pk)
        d = request.data
        try:
            campaign = campaigns.create_campaign(
                website, subject=d.get("subject", ""), body=d.get("body", ""),
                audience_source=d.get("audience_source", "all"), user=request.user)
        except campaigns.CampaignError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_campaign_dict(campaign), status=status.HTTP_201_CREATED)


class CampaignSendView(_StoreView):
    """Dispatch a drafted campaign to its real audience over the email engine."""

    def post(self, request, project_pk, pk):
        from apps.publishing import campaigns
        self.manage = True
        website = self.store(request, project_pk)
        campaign = get_object_or_404(website.campaigns, pk=pk)
        try:
            campaigns.send_campaign(campaign, user=request.user)
        except campaigns.CampaignError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_campaign_dict(campaign))
