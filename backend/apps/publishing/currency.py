"""Multi-currency (spec §24) — real formatting + deterministic conversion.

What is genuinely provided today:
  - A currency catalogue (symbol, decimal places, name) for formatting amounts
    correctly per currency.
  - Deterministic conversion using exchange rates the merchant has STORED. Integer
    cents in, integer cents out, rounded once — no floating-point drift.

What is honestly gated:
  - A LIVE exchange-rate feed. No FX provider is connected here, so rates are the
    ones the merchant entered (real, dated) — the platform never invents or guesses
    a rate. `convert` returns None when no rate is stored, and reports flag any
    amount that could not be converted rather than fabricating a figure.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# code -> (symbol, decimal places, name). Common set; extend as needed.
CURRENCIES = {
    "USD": ("$", 2, "US Dollar"),
    "EUR": ("€", 2, "Euro"),
    "GBP": ("£", 2, "British Pound"),
    "ZAR": ("R", 2, "South African Rand"),
    "AUD": ("A$", 2, "Australian Dollar"),
    "CAD": ("C$", 2, "Canadian Dollar"),
    "NGN": ("₦", 2, "Nigerian Naira"),
    "KES": ("KSh", 2, "Kenyan Shilling"),
    "INR": ("₹", 2, "Indian Rupee"),
    "JPY": ("¥", 0, "Japanese Yen"),
}


def is_supported(code: str) -> bool:
    return (code or "").upper() in CURRENCIES


def normalise(code: str) -> str:
    code = (code or "").upper()[:3]
    return code if code in CURRENCIES else "USD"


def supported_currencies() -> list[dict]:
    return [{"code": c, "symbol": s, "decimals": d, "name": n}
            for c, (s, d, n) in CURRENCIES.items()]


def format_amount(cents: int, code: str) -> str:
    """Format minor units as a display string in the given currency."""
    code = (code or "USD").upper()
    symbol, decimals, _ = CURRENCIES.get(code, ("", 2, code))
    major = Decimal(int(cents)) / (Decimal(10) ** decimals) if decimals else Decimal(int(cents))
    quant = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    value = major.quantize(quant, rounding=ROUND_HALF_UP)
    text = f"{value:,.{decimals}f}"
    sep = "" if symbol and not symbol[-1].isalnum() else " "
    return f"{symbol}{sep}{text}".strip() if symbol else f"{code} {text}"


def live_feed_status() -> dict:
    """Honest: no live FX provider is connected, so stored rates are used."""
    return {
        "connected": False,
        "detail": ("No live exchange-rate feed is connected. Conversions use the rates "
                   "you store; connect a feed to refresh them automatically."),
    }


# --- rate storage (deterministic, merchant-entered) ----------------------------
def set_rate(organization, *, base, quote, rate, user=None):
    """Store a real, dated exchange rate (1 unit base = `rate` units quote)."""
    from apps.audit.service import record as audit
    from apps.publishing.models import CurrencyRate
    base, quote = normalise(base), normalise(quote)
    rate = Decimal(str(rate))
    if rate <= 0:
        raise ValueError("Exchange rate must be greater than zero.")
    obj, _ = CurrencyRate.objects.update_or_create(
        organization=organization, base_code=base, quote_code=quote,
        defaults={"rate": rate, "source": "manual"})
    audit("currency.rate", actor=user, organization=organization,
          target=f"rate:{obj.id}", summary=f"1 {base} = {rate} {quote}")
    return obj


def get_rate(organization, base, quote) -> Decimal | None:
    """The stored rate for base→quote, 1 for identity, or None when not stored."""
    base, quote = normalise(base), normalise(quote)
    if base == quote:
        return Decimal(1)
    from apps.publishing.models import CurrencyRate
    row = CurrencyRate.objects.filter(
        organization=organization, base_code=base, quote_code=quote).first()
    if row:
        return row.rate
    # Allow the inverse if that's the one stored (1/rate), still deterministic.
    inv = CurrencyRate.objects.filter(
        organization=organization, base_code=quote, quote_code=base).first()
    if inv and inv.rate > 0:
        return (Decimal(1) / inv.rate)
    return None


def convert(cents: int, *, frm, to, organization) -> int | None:
    """Convert integer minor units frm→to using a stored rate. None if no rate —
    the caller must treat that honestly, never as zero or an assumed figure."""
    rate = get_rate(organization, frm, to)
    if rate is None:
        return None
    value = (Decimal(int(cents)) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(value)


def revenue_by_currency(website, *, base=None) -> dict:
    """Real paid-order revenue grouped by the currency it was charged in. When a base
    currency is given, also convert each bucket using stored rates — flagging any
    bucket with no rate as unconverted rather than inventing a number."""
    from apps.publishing.models import Order
    org = website.project.organization
    buckets: dict[str, int] = {}
    for o in Order.objects.filter(website=website, status="paid"):
        buckets[o.currency] = buckets.get(o.currency, 0) + o.total_cents

    rows = []
    converted_total = 0
    unconverted = []
    for code, cents in sorted(buckets.items()):
        row = {"currency": code, "total_cents": cents,
               "total_display": format_amount(cents, code)}
        if base:
            c = convert(cents, frm=code, to=base, organization=org)
            if c is None:
                row["converted"] = None
                unconverted.append(code)
            else:
                row["converted_cents"] = c
                row["converted_display"] = format_amount(c, base)
                converted_total += c
        rows.append(row)

    out = {"by_currency": rows, "currencies": len(buckets)}
    if base:
        out["base"] = base
        out["converted_total_cents"] = converted_total
        out["converted_total_display"] = format_amount(converted_total, base)
        out["unconverted"] = unconverted  # honest: rates missing for these
    return out
