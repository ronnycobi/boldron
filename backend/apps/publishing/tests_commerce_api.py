"""Tests for the merchant commerce admin API (mobile client).

Exercises the SHARED commerce engine through the authenticated merchant
endpoints: products, variants, inventory, orders, refunds, discounts, sales.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing import ecommerce_service as shop
from apps.publishing.models import Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class CommerceAdminApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="member@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Shop Org")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="Store")
        self.website = Website.objects.create(project=self.project, subdomain="store-x")

    # --- products ---
    def test_owner_creates_product(self):
        resp = self.client.post(
            reverse("commerce_api:admin-products", args=[self.project.id]),
            data={"name": "Candle", "price_cents": 1500, "track_inventory": True, "stock": 10},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Candle")
        self.assertEqual(resp.json()["stock"], 10)

    def test_member_cannot_create_product(self):
        resp = self.client.post(
            reverse("commerce_api:admin-products", args=[self.project.id]),
            data={"name": "X", "price_cents": 100},
            content_type="application/json",
            **auth(self.member),
        )
        self.assertEqual(resp.status_code, 403)

    def test_list_products(self):
        shop.create_product(self.website, name="A", price_cents=100)
        shop.create_product(self.website, name="B", price_cents=200)
        resp = self.client.get(
            reverse("commerce_api:admin-products", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_update_and_delete_product(self):
        p = shop.create_product(self.website, name="A", price_cents=100, track_inventory=True, stock=3)
        patch = self.client.patch(
            reverse("commerce_api:admin-product", args=[self.project.id, p.id]),
            data={"price_cents": 250, "active": False},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(patch.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.price_cents, 250)
        self.assertFalse(p.active)
        delete = self.client.delete(
            reverse("commerce_api:admin-product", args=[self.project.id, p.id]), **auth(self.owner)
        )
        self.assertEqual(delete.status_code, 204)

    def test_create_variant(self):
        p = shop.create_product(self.website, name="Tee", price_cents=1000)
        resp = self.client.post(
            reverse("commerce_api:admin-variants", args=[self.project.id, p.id]),
            data={"label": "Medium", "price_cents": 1200, "stock": 5},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["label"], "Medium")

    # --- inventory ---
    def test_inventory_list_and_adjust(self):
        p = shop.create_product(self.website, name="A", price_cents=100, track_inventory=True, stock=4)
        listed = self.client.get(
            reverse("commerce_api:admin-inventory", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(r["id"] == p.id and r["low"] for r in listed.json()["items"]))
        adjust = self.client.post(
            reverse("commerce_api:admin-inventory", args=[self.project.id]),
            data={"type": "product", "id": p.id, "delta": 10},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(adjust.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.stock, 14)

    # --- discounts ---
    def test_create_discount(self):
        resp = self.client.post(
            reverse("commerce_api:admin-discounts", args=[self.project.id]),
            data={"code": "SAVE10", "kind": "percent", "percent_off": 10},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["code"], "SAVE10")

    # --- orders + refund (real engine flow) ---
    def test_orders_list_detail_and_refund(self):
        p = shop.create_product(self.website, name="A", price_cents=1000, track_inventory=True, stock=5)
        order = shop.create_order(self.website, items=[{"product": p, "quantity": 2}],
                                  customer_name="Jo", customer_email="jo@x.com")
        shop.start_checkout(order, provider_key="manual")
        shop.confirm_manual_payment(order, user=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")

        listed = self.client.get(
            reverse("commerce_api:admin-orders", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        detail = self.client.get(
            reverse("commerce_api:admin-order", args=[self.project.id, order.id]), **auth(self.member)
        )
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["items"])

        refund = self.client.post(
            reverse("commerce_api:admin-order-refund", args=[self.project.id, order.id]),
            data={"reason": "changed mind"},
            content_type="application/json",
            **auth(self.owner),
        )
        self.assertEqual(refund.status_code, 200)
        self.assertEqual(refund.json()["status"], "refunded")
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)  # the 2 reserved units were restocked

    # --- sales ---
    def test_sales_summary(self):
        resp = self.client.get(
            reverse("commerce_api:admin-sales", args=[self.project.id]), **auth(self.member)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("revenue", resp.json())
        self.assertIn("counts", resp.json())

    # --- isolation / no-store ---
    def test_outsider_cannot_access(self):
        resp = self.client.get(
            reverse("commerce_api:admin-products", args=[self.project.id]), **auth(self.outsider)
        )
        self.assertEqual(resp.status_code, 404)

    def test_project_without_store_is_404(self):
        bare = Project.objects.create(organization=self.org, name="No Store")
        resp = self.client.get(
            reverse("commerce_api:admin-products", args=[bare.id]), **auth(self.owner)
        )
        self.assertEqual(resp.status_code, 404)


class MerchantInvoiceTaxApiTests(TestCase):
    """Mobile merchant invoice-by-order + tax get/set endpoints."""

    def setUp(self):
        self.owner = User.objects.create_user(email="mi-owner@x.com", password="pw12345!")
        self.member = User.objects.create_user(email="mi-member@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="MI Org")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.org.add_member(self.member, role=Role.MEMBER)
        self.project = Project.objects.create(organization=self.org, name="MI Store")
        self.website = Website.objects.create(project=self.project, subdomain="mi-store")

    def test_tax_get_set_roundtrip(self):
        # No rate yet.
        g0 = self.client.get(reverse("commerce_api:admin-tax", args=[self.project.id]),
                             **auth(self.member))
        self.assertEqual(g0.status_code, 200)
        self.assertIsNone(g0.json()["percent"])
        # Owner sets 15%.
        s = self.client.post(reverse("commerce_api:admin-tax", args=[self.project.id]),
                             data={"name": "VAT", "percent": 15},
                             content_type="application/json", **auth(self.owner))
        self.assertEqual(s.status_code, 201)
        g1 = self.client.get(reverse("commerce_api:admin-tax", args=[self.project.id]),
                             **auth(self.member)).json()
        self.assertEqual(g1["percent"], 15)
        self.assertEqual(g1["name"], "VAT")

    def test_member_cannot_set_tax(self):
        resp = self.client.post(reverse("commerce_api:admin-tax", args=[self.project.id]),
                                data={"percent": 10}, content_type="application/json",
                                **auth(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_order_invoice_returns_real_data(self):
        shop.set_tax_rate(self.website, name="VAT", percent=15, user=self.owner)
        p = shop.create_product(self.website, name="Mug", price_cents=1000)
        order = shop.create_order(self.website, items=[{"product_id": p.id, "quantity": 2}],
                                  customer_name="Ada")
        resp = self.client.get(
            reverse("commerce_api:admin-order-invoice", args=[self.project.id, order.id]),
            **auth(self.member))
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertTrue(d["number"].startswith("INV-"))
        self.assertEqual(d["total_cents"], 2300)   # 2000 + 15% VAT
        self.assertEqual(d["payment_state"], "Unpaid")

    def test_invoice_outsider_404(self):
        out = User.objects.create_user(email="mi-out@x.com", password="pw12345!")
        p = shop.create_product(self.website, name="X", price_cents=100)
        order = shop.create_order(self.website, items=[{"product_id": p.id, "quantity": 1}])
        resp = self.client.get(
            reverse("commerce_api:admin-order-invoice", args=[self.project.id, order.id]),
            **auth(out))
        self.assertEqual(resp.status_code, 404)
