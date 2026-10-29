"""Invoicing (spec §24/§32) — real invoices and receipts built from real orders.

An invoice here is never a standalone, hand-typed figure: it is a faithful
rendering of an existing :class:`~apps.publishing.models.Order` — its line items,
subtotal, discount, shipping, tax and total, plus the actual payments recorded
against it. Nothing is fabricated:

  - The payment status reflects the order's REAL state (an invoice for an unpaid
    order is clearly marked UNPAID; it only reads "paid" when a payment genuinely
    succeeded).
  - "Amount paid" and "Balance due" are computed from the Payment ledger
    (succeeded minus refunded), not assumed from the order total.

The same data drives three outputs: a structured dict (for the API / mobile),
a printable standalone HTML document, and a real PDF (via reportlab).
"""
from __future__ import annotations

import html as html_lib
import io

from django.utils import timezone


def invoice_number(order) -> str:
    """A stable invoice number derived from the order reference (which is unique),
    so the same order always yields the same invoice number."""
    ref = order.reference or ""
    if ref.startswith("ORD-"):
        return "INV-" + ref[4:]
    return "INV-" + ref if ref else f"INV-{order.pk}"


def _cents(value: int, currency: str) -> str:
    return f"{currency} {value / 100:.2f}"


def _paid_cents(order) -> tuple[int, int]:
    """(succeeded, refunded) totals from the real Payment ledger."""
    succeeded = refunded = 0
    for p in order.payments.all():
        if p.status == "succeeded":
            succeeded += p.amount_cents
        elif p.status == "refunded":
            refunded += p.amount_cents
    return succeeded, refunded


def invoice_data(order) -> dict:
    """Structured invoice built from the real order. Safe to serialise to JSON."""
    website = order.website
    project = website.project
    currency = order.currency
    succeeded, refunded = _paid_cents(order)
    net_paid = succeeded - refunded
    balance_due = max(order.total_cents - net_paid, 0)
    is_paid = order.status == "paid"
    is_refunded = order.status == "refunded"

    if is_refunded:
        payment_state = "Refunded"
    elif is_paid:
        payment_state = "Paid"
    elif balance_due <= 0 and order.total_cents:
        payment_state = "Paid"
    else:
        payment_state = "Unpaid"

    return {
        "number": invoice_number(order),
        "reference": order.reference,
        "issued_at": order.created_at.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "currency": currency,
        "status": order.status,
        "status_label": order.get_status_display(),
        "payment_state": payment_state,
        "is_paid": is_paid or (balance_due <= 0 and order.total_cents > 0),
        "seller": {
            "name": project.name,
            "organization": project.organization.name,
            "store": website.subdomain,
        },
        "buyer": {
            "name": order.customer_name,
            "email": order.customer_email,
            "address": order.shipping_address,
        },
        "items": [
            {
                "name": it.name,
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "unit_price_display": _cents(it.unit_price_cents, currency),
                "line_total_cents": it.line_total_cents,
                "line_total_display": _cents(it.line_total_cents, currency),
            }
            for it in order.items.all()
        ],
        "subtotal_cents": order.subtotal_cents,
        "subtotal_display": _cents(order.subtotal_cents, currency),
        "discount_cents": order.discount_cents,
        "discount_display": _cents(order.discount_cents, currency),
        "shipping_cents": order.shipping_cents,
        "shipping_display": _cents(order.shipping_cents, currency),
        "tax_cents": order.tax_cents,
        "tax_display": _cents(order.tax_cents, currency),
        "tax_label": order.tax_rate.name if order.tax_rate_id else "Tax",
        "total_cents": order.total_cents,
        "total_display": _cents(order.total_cents, currency),
        "amount_paid_cents": net_paid,
        "amount_paid_display": _cents(max(net_paid, 0), currency),
        "balance_due_cents": balance_due,
        "balance_due_display": _cents(balance_due, currency),
        "payments": [
            {
                "provider": p.provider,
                "method": p.method,
                "amount_display": _cents(p.amount_cents, currency),
                "status": p.status,
                "status_label": p.get_status_display(),
                "created_at": p.created_at.isoformat(),
            }
            for p in order.payments.all()
        ],
    }


# --- HTML (standalone, printable) ---------------------------------------------
def render_invoice_html(order) -> str:
    d = invoice_data(order)
    e = html_lib.escape

    rows = "".join(
        f"<tr><td>{e(i['name'])}</td>"
        f"<td class='num'>{i['quantity']}</td>"
        f"<td class='num'>{e(i['unit_price_display'])}</td>"
        f"<td class='num'>{e(i['line_total_display'])}</td></tr>"
        for i in d["items"]
    ) or "<tr><td colspan='4' class='muted'>No items.</td></tr>"

    totals = [("Subtotal", d["subtotal_display"], False)]
    if d["discount_cents"]:
        totals.append(("Discount", "-" + d["discount_display"], False))
    if d["shipping_cents"]:
        totals.append(("Shipping", d["shipping_display"], False))
    if d["tax_cents"]:
        totals.append((d["tax_label"], d["tax_display"], False))
    totals.append(("Total", d["total_display"], True))
    if d["amount_paid_cents"]:
        totals.append(("Amount paid", "-" + d["amount_paid_display"], False))
        totals.append(("Balance due", d["balance_due_display"], True))
    totals_html = "".join(
        f"<tr class='{'grand' if strong else ''}'><td>{e(label)}</td>"
        f"<td class='num'>{e(val)}</td></tr>"
        for label, val, strong in totals
    )

    buyer_lines = []
    if d["buyer"]["name"]:
        buyer_lines.append(e(d["buyer"]["name"]))
    if d["buyer"]["email"]:
        buyer_lines.append(e(d["buyer"]["email"]))
    if d["buyer"]["address"]:
        buyer_lines.append(e(d["buyer"]["address"]).replace("\n", "<br>"))
    buyer_html = "<br>".join(buyer_lines) or "<span class='muted'>—</span>"

    state = d["payment_state"]
    state_class = {"Paid": "paid", "Refunded": "refunded"}.get(state, "unpaid")
    issued = order.created_at.strftime("%B %-d, %Y")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(d['number'])} · {e(d['seller']['name'])}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font: 14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
         color:#1a1d24; background:#f4f5f7; margin:0; padding:24px; }}
  .sheet {{ max-width:720px; margin:0 auto; background:#fff; border:1px solid #e4e6eb;
           border-radius:12px; padding:36px 40px; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start;
          gap:16px; flex-wrap:wrap; border-bottom:1px solid #eceef2; padding-bottom:20px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  .muted {{ color:#6a7180; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .stamp {{ font-size:12px; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
           padding:4px 12px; border-radius:99px; border:1.5px solid; }}
  .stamp.paid {{ color:#1a7f47; border-color:#1a7f47; }}
  .stamp.unpaid {{ color:#b26a00; border-color:#b26a00; }}
  .stamp.refunded {{ color:#7a7f8a; border-color:#7a7f8a; }}
  .parties {{ display:flex; gap:40px; flex-wrap:wrap; margin:22px 0; }}
  .parties h3 {{ font-size:11px; text-transform:uppercase; letter-spacing:1px;
                color:#8a909c; margin:0 0 6px; }}
  table {{ width:100%; border-collapse:collapse; }}
  .items th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.6px;
              color:#8a909c; border-bottom:1px solid #eceef2; padding:8px 0; }}
  .items td {{ padding:9px 0; border-bottom:1px solid #f1f2f5; }}
  .items th.num, .items td.num {{ text-align:right; }}
  .totals {{ margin-left:auto; width:280px; margin-top:16px; }}
  .totals td {{ padding:5px 0; }}
  .totals tr.grand td {{ font-weight:700; font-size:16px; border-top:2px solid #1a1d24;
                        padding-top:10px; }}
  .foot {{ margin-top:28px; padding-top:16px; border-top:1px solid #eceef2;
          font-size:12px; color:#8a909c; }}
  @media print {{ body {{ background:#fff; padding:0; }} .sheet {{ border:0; }} }}
</style></head>
<body><div class="sheet">
  <div class="head">
    <div>
      <h1>Invoice</h1>
      <div class="muted">{e(d['number'])}</div>
      <div class="muted">Order {e(d['reference'])}</div>
      <div class="muted">Issued {e(issued)}</div>
    </div>
    <div style="text-align:right">
      <div style="font-weight:700;font-size:16px">{e(d['seller']['name'])}</div>
      <div class="muted">{e(d['seller']['organization'])}</div>
      <div style="margin-top:10px"><span class="stamp {state_class}">{e(state)}</span></div>
    </div>
  </div>

  <div class="parties">
    <div><h3>Billed to</h3>{buyer_html}</div>
  </div>

  <table class="items">
    <tr><th>Item</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr>
    {rows}
  </table>

  <table class="totals">{totals_html}</table>

  <div class="foot">Invoice generated by {e(d['seller']['name'])} from order {e(d['reference'])}.
    Figures reflect the recorded order and payments.</div>
</div></body></html>
"""


# --- PDF (real, via reportlab) ------------------------------------------------
def render_invoice_pdf(order) -> bytes:
    """A genuine PDF invoice built from the same real order data."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    d = invoice_data(order)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left = 20 * mm
    right = width - 20 * mm
    y = height - 24 * mm

    c.setFont("Helvetica-Bold", 20)
    c.drawString(left, y, "Invoice")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right, y, d["seller"]["name"])
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#6a7180"))
    c.drawString(left, y, d["number"])
    c.drawRightString(right, y, d["seller"]["organization"])
    y -= 5 * mm
    c.drawString(left, y, f"Order {d['reference']}")
    issued = order.created_at.strftime("%B %d, %Y")
    c.drawRightString(right, y, f"{d['payment_state'].upper()}  ·  issued {issued}")
    c.setFillColor(colors.black)
    y -= 10 * mm

    if d["buyer"]["name"] or d["buyer"]["email"]:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#8a909c"))
        c.drawString(left, y, "BILLED TO")
        c.setFillColor(colors.black)
        y -= 5 * mm
        c.setFont("Helvetica", 10)
        for line in filter(None, [d["buyer"]["name"], d["buyer"]["email"]]):
            c.drawString(left, y, line)
            y -= 5 * mm
        y -= 3 * mm

    # Items header
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#8a909c"))
    c.drawString(left, y, "ITEM")
    c.drawRightString(right - 70 * mm, y, "QTY")
    c.drawRightString(right - 35 * mm, y, "UNIT")
    c.drawRightString(right, y, "AMOUNT")
    c.setFillColor(colors.black)
    y -= 2 * mm
    c.line(left, y, right, y)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    for i in d["items"]:
        c.drawString(left, y, (i["name"] or "")[:48])
        c.drawRightString(right - 70 * mm, y, str(i["quantity"]))
        c.drawRightString(right - 35 * mm, y, i["unit_price_display"])
        c.drawRightString(right, y, i["line_total_display"])
        y -= 6 * mm

    y -= 2 * mm
    c.line(right - 80 * mm, y, right, y)
    y -= 7 * mm

    def total_row(label, value, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(right - 35 * mm, y, label)
        c.drawRightString(right, y, value)
        y -= 6 * mm

    total_row("Subtotal", d["subtotal_display"])
    if d["discount_cents"]:
        total_row("Discount", "-" + d["discount_display"])
    if d["shipping_cents"]:
        total_row("Shipping", d["shipping_display"])
    if d["tax_cents"]:
        total_row(d["tax_label"], d["tax_display"])
    total_row("Total", d["total_display"], bold=True)
    if d["amount_paid_cents"]:
        total_row("Amount paid", "-" + d["amount_paid_display"])
        total_row("Balance due", d["balance_due_display"], bold=True)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#8a909c"))
    c.drawString(left, 18 * mm,
                 f"Generated from order {d['reference']}. Figures reflect the recorded order and payments.")
    c.showPage()
    c.save()
    return buf.getvalue()
