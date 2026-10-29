"""The Mobile Build Planner (spec §5, §33, §48).

Turns a plain-language mobile-app brief into a structured, HONEST plan:

  DESCRIBE → UNDERSTAND → PLAN

  - which mobile capabilities the app needs (grouped, with honest status),
  - the device permissions it will ask for, and why (spec §33),
  - the target platforms (iOS / Android / Huawei) and per-platform notes (spec §32),
  - an honest summary: how much the engine generates today vs what's gated on
    connected credentials/infra vs what's still planned.

Deterministic and offline: keyword rules map what the customer said to mobile
capability ids, on top of a baseline every app gets. An AI pass (the Mobile Agent,
apps.mobile.agent) can refine the screen design later — but the plan here never
claims a build, a signing, or a store submission happened; those are real, gated
steps owned by apps.release.
"""
from __future__ import annotations

import re

from apps.mobile import capabilities as caps

# Every mobile app gets these (the generated shell: screens, navigation, theme,
# auth against the backend, the API client and secure local storage).
_BASELINE = ["screens", "navigation", "design_system", "auth", "sessions",
             "api", "database", "local_storage"]

_ALL_PLATFORMS = ["ios", "android", "huawei"]
_PLATFORM_NAMES = {"ios": "iOS", "android": "Android", "huawei": "Huawei AppGallery"}

# (capability id, regex over the lowered brief)
_RULES = [
    ("forms", r"\bform|submit|capture|log |record|register|entry|checklist\b"),
    ("lists", r"\blist|search|filter|browse|directory|feed\b"),
    ("tables", r"\btable|spreadsheet|rows|grid\b"),
    ("charts", r"\bchart|graph|kpi|metric|report|insight|trend\b"),
    ("dashboards", r"\bdashboard|overview|progress|cost|summary\b"),
    ("mfa", r"\bmfa|two[- ]factor|2fa|otp|authenticator\b"),
    ("biometric", r"\bbiometric|face id|touch id|fingerprint|unlock\b"),
    ("oauth", r"\bgoogle sign|apple sign|microsoft|sso|single sign|social login\b"),
    ("offline", r"\boffline|sync|no signal|field|remote area|intermittent\b"),
    ("camera", r"\bcamera|photo|scan|picture|capture image|snapshot\b"),
    ("gallery", r"\bupload|gallery|attach|document|file|image\b"),
    ("location", r"\bgps|location|site|geo|map|track|delivery|route|coordinates\b"),
    ("media", r"\baudio|video|voice|record(ing)?\b"),
    ("nfc", r"\bnfc|tap to|tag\b"),
    ("bluetooth", r"\bbluetooth|ble|beacon\b"),
    ("push", r"\bpush|notification|alert|remind\b"),
    ("deep_links", r"\bdeep link|open directly|universal link|app link\b"),
    ("sharing", r"\bshare|sharing\b"),
    ("commerce", r"\bshop|store|e-?commerce|product|cart|order|catalog|marketplace\b"),
    ("payments", r"\bpay|payment|checkout|card|billing\b"),
    ("subscriptions", r"\bsubscription|recurring|membership|monthly plan\b"),
    ("invoicing", r"\binvoice|receipt|quote\b"),
    ("analytics", r"\banalytics|usage|conversion|retention|track events\b"),
    ("crash_monitoring", r"\bcrash|error monitoring|stability|performance monitoring\b"),
    ("store_submission", r"\bpublish|app store|play store|appgallery|release to\b"),
]


def capability_ids(brief: str) -> list[str]:
    text = (brief or "").lower()
    ids = list(_BASELINE)
    for cap_id, pattern in _RULES:
        if re.search(pattern, text) and cap_id not in ids:
            ids.append(cap_id)
    # Capture-in-the-field (camera + location) implies offline + sync (spec §5, §10).
    if "camera" in ids and "location" in ids and "offline" not in ids:
        ids.append("offline")
    # A dashboard is charts + KPIs (spec §19, §20).
    if "dashboards" in ids and "charts" not in ids:
        ids.append("charts")
    # Commerce implies invoicing + versioning/store surfaces are worth planning for.
    if "commerce" in ids:
        for extra in ("payments", "invoicing"):
            if extra not in ids:
                ids.append(extra)
    # Every planned app benefits from the release surfaces being represented.
    for rel in ("versioning", "store_metadata", "store_submission", "signing",
                "app_updates"):
        if rel not in ids:
            ids.append(rel)
    return [i for i in ids if caps.get(i) is not None]


def _normalise_platforms(platforms) -> list[str]:
    if not platforms:
        return list(_ALL_PLATFORMS)
    out = [p for p in _ALL_PLATFORMS if p in {str(x).lower() for x in platforms}]
    return out or list(_ALL_PLATFORMS)


def plan(brief: str, *, platforms=None) -> dict:
    """The structured mobile build plan for a brief (spec §48)."""
    ids = capability_ids(brief)
    selected = [caps.get(i) for i in ids]
    platforms = _normalise_platforms(platforms)

    # Group the capabilities, honest status per item.
    grouped = []
    for group, _items in caps.by_group():
        picked = [c for c in selected if c.group == group]
        if not picked:
            continue
        grouped.append({
            "group": group,
            "items": [{
                "id": c.id, "name": c.name, "status": c.status,
                "generated": c.is_generated, "summary": c.summary,
                "platform_notes": c.platform_notes,
            } for c in picked],
        })

    # Device permissions this app will request, de-duplicated, each with a reason.
    perm_ids: list[str] = []
    for c in selected:
        for p in c.permissions:
            if p not in perm_ids:
                perm_ids.append(p)
    permissions = []
    for pid in perm_ids:
        dp = caps.permission(pid)
        if dp:
            permissions.append({"id": dp.id, "name": dp.name, "rationale": dp.rationale})

    generated = [c for c in selected if c.status == caps.GENERATED]
    gated = [c for c in selected if c.status == caps.GATED]
    planned = [c for c in selected if c.status == caps.PLANNED]

    return {
        "platforms": [{"id": p, "name": _PLATFORM_NAMES[p]} for p in platforms],
        "groups": grouped,
        "permissions": permissions,
        "summary": {
            "total": len(selected),
            "generated_count": len(generated),
            "gated_count": len(gated),
            "planned_count": len(planned),
            "gated_names": [c.name for c in gated],
            "planned_names": [c.name for c in planned],
        },
        # Honest statement of what this plan is and isn't.
        "disclosure": (
            "This plan describes the app the engine will design and scaffold. "
            "Building, signing and submitting to the stores are real, separate steps "
            "that need your connected developer accounts — they are never performed "
            "or reported as done without them."
        ),
    }
