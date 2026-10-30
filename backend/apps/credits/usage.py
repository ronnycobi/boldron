"""Composed usage overview (spec §17) — the org's resource meters in one place.

Honest meters: AI credits have a real plan allowance, so they show a genuine used %;
storage, projects and team members are real counts without a plan limit here, so they
are shown as amounts/counts, never a fabricated percentage. Nothing is invented — every
figure comes from a real record.
"""
from __future__ import annotations

from decimal import Decimal


def _storage_bytes(organization) -> int:
    from apps.files.models import StoredFile
    return sum(f.size for f in StoredFile.objects.filter(organization=organization).only("size"))


def _bytes_display(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def usage_overview(organization) -> dict:
    """The org's usage meters, customer-safe (spec §17)."""
    from apps.credits.catalog import billing_summary
    billing = billing_summary(organization)
    allowance = billing.get("allowance") or Decimal("0")
    balance = billing.get("balance") or Decimal("0")
    unlimited = not allowance or allowance == 0

    credits = {
        "plan": billing.get("plan"),
        "unlimited": bool(unlimited),
        "allowance": str(allowance),
        "balance": str(balance),
        # Used % only makes sense with a real allowance.
        "used_pct": None if unlimited
        else int(max(0, min(100, (allowance - balance) / allowance * 100))),
    }
    storage_bytes = _storage_bytes(organization)
    return {
        "organization": {"id": organization.id, "name": organization.name},
        "credits": credits,
        "storage": {"bytes": storage_bytes, "display": _bytes_display(storage_bytes)},
        "projects": organization.projects.count(),
        "members": organization.memberships.count(),
    }
