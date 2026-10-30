"""Browser & device compatibility analysis (spec §9, §31).

Honesty first: certifying that an app runs on real Chrome / Safari / Firefox / Edge
and on real iOS / Android / Huawei devices needs those actual browsers and a device
cloud — infrastructure that isn't connected here. So this module NEVER emits a fake
"✓ passes on X". Instead it does what it genuinely can offline: a deterministic
STATIC analysis of the app's own code that surfaces real compatibility RISKS (e.g.
Google-service dependencies that won't work on Huawei, browser-only APIs, a missing
mobile viewport), tagged with the targets each risk affects.

Each target is reported as either `risk` (analysis found something) or `unverified`
(nothing found statically, but it has NOT been run on a real browser/device) — never
`ok`/passed, because that can only be proven by a live run on a connected test
environment, which is honestly reported as not connected.
"""
from __future__ import annotations

import re

from apps.repositories.service import repo_for_project

BROWSERS = [
    {"id": "chrome", "name": "Chrome"},
    {"id": "safari", "name": "Safari"},
    {"id": "firefox", "name": "Firefox"},
    {"id": "edge", "name": "Edge"},
]
PLATFORMS = [
    {"id": "ios", "name": "iOS"},
    {"id": "android", "name": "Android"},
    {"id": "huawei", "name": "Huawei AppGallery"},
]

_SCAN_EXT = (".js", ".jsx", ".ts", ".tsx", ".dart", ".html", ".css", ".kt",
             ".java", ".gradle", ".xml", ".json", ".swift", ".vue", ".svelte")

# (compiled regex, affected target ids, message). Each is a REAL, specific risk.
_RULES = [
    # --- Google services → break on Huawei (no GMS); spec §31 headline ---
    (re.compile(r"com\.google\.firebase|firebase/messaging|getMessaging\(|FirebaseMessaging"),
     ["huawei"], "Uses Firebase Cloud Messaging — Huawei devices need HMS Push Kit instead."),
    (re.compile(r"maps\.googleapis\.com|com\.google\.android\.gms\.maps|GoogleMap\b|google_maps_flutter"),
     ["huawei"], "Uses Google Maps — Huawei devices need Petal/HMS Map Kit."),
    (re.compile(r"com\.google\.android\.gms\.auth|GoogleSignIn|accounts\.google\.com|google_sign_in"),
     ["huawei"], "Uses Google Sign-In — Huawei devices need HMS Account Kit."),
    (re.compile(r"com\.android\.billingclient|BillingClient|in_app_purchase.*google"),
     ["huawei"], "Uses Google Play Billing — Huawei devices need Huawei IAP."),
    (re.compile(r"com\.google\.android\.gms(?![.\w]*maps|[.\w]*auth)"),
     ["huawei"], "Depends on Google Play Services — not available on Huawei devices."),
    # --- Browser-only web APIs → risk on Safari / Firefox ---
    (re.compile(r"\bnavigator\.usb\b|\bWebUSB\b"),
     ["safari", "firefox"], "Uses WebUSB — not supported in Safari or Firefox."),
    (re.compile(r"\bnavigator\.bluetooth\b|\bWeb Bluetooth\b"),
     ["safari", "firefox"], "Uses Web Bluetooth — not supported in Safari or Firefox."),
    (re.compile(r"\bshowDirectoryPicker\b|\bshowOpenFilePicker\b"),
     ["safari", "firefox"], "Uses the File System Access API — Chromium-only."),
    (re.compile(r"\bBarcodeDetector\b"),
     ["safari", "firefox"], "Uses BarcodeDetector — Chromium-only."),
    (re.compile(r"\bwebkitSpeechRecognition\b"),
     ["firefox"], "Uses webkitSpeechRecognition — not supported in Firefox."),
    (re.compile(r"\bActiveXObject\b|\bdocument\.all\b"),
     ["chrome", "safari", "firefox"], "Uses a legacy IE-only API that no modern browser supports."),
    # --- Responsive / mobile layout ---
    (re.compile(r"(?:min-)?width\s*:\s*(?:1[0-9]{3,}|[2-9][0-9]{2,})px"),
     ["ios", "android", "huawei"], "Hard-coded wide fixed pixel widths can break small screens."),
]
_VIEWPORT_RE = re.compile(r'<meta[^>]+name=["\']viewport["\']', re.I)


def _read_files(project) -> dict[str, str]:
    repo = repo_for_project(project)
    if not repo.is_initialized:
        return {}
    files = {}
    for rel in repo.list_files():
        if not rel.lower().endswith(_SCAN_EXT):
            continue
        try:
            files[rel] = (repo.path / rel).read_text()
        except (OSError, UnicodeDecodeError):
            continue
    return files


def _detect_risks(files: dict[str, str]) -> list[dict]:
    risks: list[dict] = []
    seen = set()
    for path, content in files.items():
        for rx, targets, message in _RULES:
            if rx.search(content):
                key = (message, path)
                if key in seen:
                    continue
                seen.add(key)
                risks.append({"message": message, "targets": targets, "path": path})
    # A missing mobile viewport affects every mobile target (only if there's HTML).
    html = {p: c for p, c in files.items() if p.lower().endswith(".html")}
    if html and not any(_VIEWPORT_RE.search(c) for c in html.values()):
        risks.append({
            "message": "No mobile viewport meta tag — pages may not scale on phones.",
            "targets": ["ios", "android", "huawei"], "path": "(html)",
        })
    return risks


def live_testing_status() -> dict:
    """Honest: no browser/device cloud is connected, so live runs can't happen."""
    return {
        "connected": False,
        "detail": ("Running the app on real browsers and devices needs a connected "
                   "test environment. None is connected, so targets without a static "
                   "risk are shown as not verified — never as passed."),
    }


def compatibility_report(project) -> dict:
    """A customer-safe compatibility report: per-target risks, honestly unverified
    where nothing was found, and the gated live-testing status (spec §9)."""
    files = _read_files(project)
    analysed = bool(files)
    risks = _detect_risks(files) if analysed else []

    def _target_rows(targets):
        rows = []
        for t in targets:
            t_risks = [r["message"] for r in risks if t["id"] in r["targets"]]
            rows.append({
                "id": t["id"], "name": t["name"],
                # Never "ok": only "risk" (found something) or "unverified".
                "status": "risk" if t_risks else "unverified",
                "risks": t_risks,
            })
        return rows

    return {
        "analysed": analysed,
        "note": ("No code to analyse yet." if not analysed else
                 "Static analysis of your app's code. It flags real compatibility "
                 "risks; it cannot certify a target passes without a live run."),
        "browsers": _target_rows(BROWSERS),
        "platforms": _target_rows(PLATFORMS),
        "risks": risks,
        "risk_count": len(risks),
        "live_testing": live_testing_status(),
    }
