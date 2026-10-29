"""Invoicing: real invoices/receipts generated from real orders.

Invoices must reflect the recorded order and its payments — never a fabricated
"paid" status or an invented figure. These tests pin that honesty.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.api import issue_tokens
from apps.organizations.models import Organization, Role
from apps.projects.models import Project
from apps.publishing import ecommerce_service as shop
from apps.publishing import invoicing
from apps.publishing.models import Website

User = get_user_model()


def auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(user)['access']}"}


class InvoiceDataTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Acme")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Acme Store")
        self.website = Website.objects.create(project=self.project, subdomain="acme")
        self.product = shop.create_product(self.website, name="Mug", price_cents=1500, currency="USD")
        self.order = shop.create_order(
            self.website, items=[{"product_id": self.product.id, "quantity": 2}],
            customer_name="Sam Buyer", customer_email="sam@example.com")

    def test_invoice_number_is_stable_and_derived_from_reference(self):
        n1 = invoicing.invoice_number(self.order)
        n2 = invoicing.invoice_number(self.order)
        self.assertEqual(n1, n2)
        self.assertTrue(n1.startswith("INV-"))
        self.assertIn(self.order.reference[4:], n1)

    def test_data_reflects_real_order_totals(self):
        d = invoicing.invoice_data(self.order)
        self.assertEqual(d["total_cents"], self.order.total_cents)
        self.assertEqual(d["subtotal_cents"], 3000)
        self.assertEqual(len(d["items"]), 1)
        self.assertEqual(d["items"][0]["quantity"], 2)
        self.assertEqual(d["items"][0]["line_total_cents"], 3000)

    def test_unpaid_order_invoice_is_marked_unpaid(self):
        # A freshly created order has not been paid — the invoice must say so.
        d = invoicing.invoice_data(self.order)
        self.assertEqual(d["payment_state"], "Unpaid")
        self.assertFalse(d["is_paid"])
        self.assertEqual(d["balance_due_cents"], self.order.total_cents)

    def test_paid_order_invoice_reflects_real_payment(self):
        shop.start_checkout(self.order, provider_key="manual")
        shop.confirm_manual_payment(self.order, user=self.owner)
        self.order.refresh_from_db()
        d = invoicing.invoice_data(self.order)
        self.assertEqual(d["payment_state"], "Paid")
        self.assertTrue(d["is_paid"])
        self.assertEqual(d["amount_paid_cents"], self.order.total_cents)
        self.assertEqual(d["balance_due_cents"], 0)

    def test_html_is_a_document_with_the_real_figures(self):
        html = invoicing.render_invoice_html(self.order)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn(invoicing.invoice_number(self.order), html)
        self.assertIn("Sam Buyer", html)
        self.assertIn(self.order.total_display, html)
        self.assertIn("UNPAID", html.upper())

    def test_pdf_is_a_real_pdf(self):
        pdf = invoicing.render_invoice_pdf(self.order)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 500)

    def test_capability_is_available(self):
        from apps.capabilities.registry import get
        self.assertTrue(get("invoicing").is_available)


class InvoiceSurfaceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="o2@x.com", password="pw12345!")
        self.outsider = User.objects.create_user(email="out@x.com", password="pw12345!")
        self.org = Organization.objects.create(name="Org2")
        self.org.add_member(self.owner, role=Role.OWNER)
        self.project = Project.objects.create(organization=self.org, name="Shop2")
        self.website = Website.objects.create(project=self.project, subdomain="shop2")
        self.product = shop.create_product(self.website, name="Hat", price_cents=2000)
        self.order = shop.create_order(
            self.website, items=[{"product_id": self.product.id, "quantity": 1}],
            customer_name="Pat", customer_email="pat@example.com")

    def test_dashboard_invoice_html(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("dashboard:order_invoice", args=[self.project.id, self.order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/html")
        self.assertIn(invoicing.invoice_number(self.order), resp.content.decode())

    def test_dashboard_invoice_pdf(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("dashboard:order_invoice", args=[self.project.id, self.order.id]),
            {"format": "pdf"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_dashboard_invoice_denies_outsider(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(
            reverse("dashboard:order_invoice", args=[self.project.id, self.order.id]))
        self.assertEqual(resp.status_code, 404)

    def test_public_invoice_api_returns_real_data(self):
        resp = self.client.get(
            reverse("commerce_api:order-invoice",
                    args=[self.website.subdomain, self.order.reference]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["reference"], self.order.reference)
        self.assertEqual(data["total_cents"], self.order.total_cents)
        self.assertEqual(data["payment_state"], "Unpaid")

    def test_public_invoice_api_404_for_unknown(self):
        resp = self.client.get(
            reverse("commerce_api:order-invoice", args=[self.website.subdomain, "ORD-NOPE"]))
        self.assertEqual(resp.status_code, 404)
