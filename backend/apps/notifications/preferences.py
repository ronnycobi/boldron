"""Notification-preference helpers.

`wants(user, category)` is checked at real send points before dispatching an
optional email. It defaults to True (opt-out model) and fails open — a missing
or unreadable preference never silently drops mail.
"""
from __future__ import annotations

from apps.notifications.models import NotificationPreference

# Categories exposed in settings. Each maps to a real, optional email sender.
CATEGORIES = [
    {"key": "support_updates", "label": "Support updates",
     "description": "Confirmations and replies on your support tickets."},
]
CATEGORY_KEYS = [c["key"] for c in CATEGORIES]


def wants(user, category: str) -> bool:
    if user is None or not getattr(user, "pk", None):
        return True  # no user to check — don't suppress
    if category not in CATEGORY_KEYS:
        return True  # unknown/un-gated category always sends
    pref = NotificationPreference.objects.filter(user=user).first()
    if pref is None:
        return True
    return bool(getattr(pref, category, True))


def as_dict(user) -> dict:
    pref, _ = NotificationPreference.objects.get_or_create(user=user)
    return {c["key"]: bool(getattr(pref, c["key"])) for c in CATEGORIES}


def update(user, values: dict) -> dict:
    pref, _ = NotificationPreference.objects.get_or_create(user=user)
    changed = []
    for c in CATEGORY_KEYS:
        if c in values:
            setattr(pref, c, bool(values[c]))
            changed.append(c)
    if changed:
        pref.save(update_fields=changed + ["updated_at"])
    return as_dict(user)
