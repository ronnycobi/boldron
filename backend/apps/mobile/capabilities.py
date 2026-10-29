"""The Mobile Capability Registry (spec §4) — the building blocks a generated
mobile application can be given, grouped, each with an HONEST status.

This is the mobile counterpart to apps.capabilities (the web/app registry). A
customer describes a mobile app in plain language; the planner (planner.py) infers
which of these capabilities the app needs instead of making them configure each.

Honesty is the whole point (CLAUDE.md): the status never claims more than the
platform truly does.

  - "generated"  : the engine genuinely designs/scaffolds this into the app spec —
                   screens, navigation, forms, lists, API/auth wiring against the
                   shared backend, commerce over the shared engine, etc. The mobile
                   toolchain (Dart/Swift) is NOT in the build sandbox, so a generated
                   capability is a real design + scaffold, not a compiled binary; the
                   actual build/sign/package steps live in apps.release and are gated.
  - "gated"      : the machinery exists but activation needs connected credentials or
                   device/runtime infra that isn't here — push providers (APNs/FCM/
                   HMS), OAuth, biometrics on a real device, app signing, store
                   submission. It refuses honestly until connected; it never fakes.
  - "planned"    : on the roadmap, not provided yet.

Device permissions a capability needs are declared here too (spec §33), so the
plan can show exactly what the app will ask the user for, and why.
"""
from __future__ import annotations

from dataclasses import dataclass, field

GENERATED = "generated"
GATED = "gated"
PLANNED = "planned"

# Capability groups, in display order (spec §4).
GROUPS = ["UI", "Auth", "Data", "Device", "Communication", "Commerce",
          "Analytics", "Release"]


@dataclass(frozen=True)
class MobileCapability:
    id: str
    name: str
    group: str
    status: str
    summary: str
    # Device permissions (ids into PERMISSIONS) this capability requires.
    permissions: tuple[str, ...] = ()
    # Per-platform notes where the three platforms genuinely differ (spec §32).
    platform_notes: dict = field(default_factory=dict)

    @property
    def is_generated(self) -> bool:
        return self.status == GENERATED


# --- device permissions (spec §33) ---------------------------------------------
@dataclass(frozen=True)
class DevicePermission:
    id: str
    name: str
    rationale: str   # plain-language why, shown to the user at request time


PERMISSIONS = {
    "camera": DevicePermission("camera", "Camera",
                               "Take photos or scan documents inside the app."),
    "microphone": DevicePermission("microphone", "Microphone",
                                   "Record audio for voice notes or calls."),
    "location": DevicePermission("location", "Location",
                                 "Verify a site, tag a record, or show nearby results."),
    "notifications": DevicePermission("notifications", "Notifications",
                                      "Send you alerts about orders, jobs and messages."),
    "photos": DevicePermission("photos", "Photo library",
                               "Attach images from your gallery."),
    "files": DevicePermission("files", "Files",
                              "Attach and open documents."),
    "contacts": DevicePermission("contacts", "Contacts",
                                 "Fill in people you already know (only when you ask)."),
    "bluetooth": DevicePermission("bluetooth", "Bluetooth",
                                  "Connect to nearby supported devices."),
    "nfc": DevicePermission("nfc", "NFC",
                            "Read supported tags or cards by tapping."),
    "biometric": DevicePermission("biometric", "Face ID / fingerprint",
                                  "Unlock the app and confirm sensitive actions."),
}


def _notes(ios="", android="", huawei=""):
    d = {}
    if ios:
        d["ios"] = ios
    if android:
        d["android"] = android
    if huawei:
        d["huawei"] = huawei
    return d


# --- the catalogue -------------------------------------------------------------
_CATALOG = [
    # UI (spec §6, §7, §19, §20)
    MobileCapability("screens", "Screens", "UI", GENERATED,
                     "Native screens with safe areas, loading / empty / error states."),
    MobileCapability("navigation", "Navigation", "UI", GENERATED,
                     "Stacks, tabs, drawers and modal screens — native touch navigation."),
    MobileCapability("forms", "Forms", "UI", GENERATED,
                     "Validated forms with native keyboards and inline errors."),
    MobileCapability("lists", "Lists & search", "UI", GENERATED,
                     "Lists with search, filters, pull-to-refresh and swipe actions."),
    MobileCapability("tables", "Tables (mobile layout)", "UI", GENERATED,
                     "Tabular data as mobile cards/lists — never a squeezed desktop table."),
    MobileCapability("charts", "Charts & KPIs", "UI", GENERATED,
                     "Line/bar/pie/area charts and KPI cards over real app data."),
    MobileCapability("dashboards", "Dashboards", "UI", GENERATED,
                     "KPI cards, charts and filtered reports laid out for mobile."),
    MobileCapability("design_system", "Design system", "UI", GENERATED,
                     "Consistent components, light/dark theme, spacing and typography."),

    # Auth (spec §8, §9)
    MobileCapability("auth", "Authentication", "Auth", GENERATED,
                     "Email/password sign-in, registration, reset — against the shared backend."),
    MobileCapability("sessions", "Sessions", "Auth", GENERATED,
                     "Token sessions with refresh; tokens held in secure device storage."),
    MobileCapability("mfa", "Multi-factor", "Auth", GENERATED,
                     "Time-based codes and recovery, verified server-side."),
    MobileCapability("biometric", "Biometric unlock", "Auth", GATED,
                     "Face ID / fingerprint to unlock and re-authenticate — needs a real device; "
                     "never a substitute for server-side authorization.",
                     permissions=("biometric",)),
    MobileCapability("oauth", "Social / SSO sign-in", "Auth", GATED,
                     "Google / Apple / Microsoft sign-in — activates when that provider is connected.",
                     platform_notes=_notes(
                         ios="Apple Sign In is required when other social logins are offered.",
                         huawei="Use Huawei Account Kit where Google sign-in is unavailable.")),

    # Data (spec §10, §16, §18)
    MobileCapability("api", "API client", "Data", GENERATED,
                     "One central client: auth, token refresh, retries, errors, pagination, timeouts."),
    MobileCapability("database", "Database access", "Data", GENERATED,
                     "Reads/writes go through the backend — the single source of truth."),
    MobileCapability("local_storage", "Secure local storage", "Data", GENERATED,
                     "Tokens and small secrets in platform secure storage, not plain preferences."),
    MobileCapability("offline", "Offline & sync", "Data", GENERATED,
                     "Cache, queued changes, synchronisation, retry and conflict handling."),

    # Device (spec §11, §12, §13, §33)
    MobileCapability("camera", "Camera", "Device", GENERATED,
                     "Capture, preview, compress and upload photos; document scan where supported.",
                     permissions=("camera",)),
    MobileCapability("gallery", "Photos & files", "Device", GENERATED,
                     "Pick images and documents with upload progress, retry and offline queue.",
                     permissions=("photos", "files")),
    MobileCapability("location", "Location / GPS", "Device", GENERATED,
                     "Current location, site verification, tracking — permission requested with a reason.",
                     permissions=("location",)),
    MobileCapability("media", "Audio / video", "Device", GENERATED,
                     "Record and attach audio/video with compression and access control.",
                     permissions=("microphone",)),
    MobileCapability("device_info", "Device info", "Device", GENERATED,
                     "Platform, OS version and app version for support and analytics."),
    MobileCapability("nfc", "NFC", "Device", GATED,
                     "Read supported tags where the device and OS allow it.",
                     permissions=("nfc",)),
    MobileCapability("bluetooth", "Bluetooth", "Device", GATED,
                     "Connect to nearby supported devices where available.",
                     permissions=("bluetooth",)),

    # Communication (spec §14, §15)
    MobileCapability("push", "Push notifications", "Communication", GATED,
                     "Device push with preferences, categories, history and deep links — activates "
                     "when a push provider is connected.",
                     permissions=("notifications",),
                     platform_notes=_notes(ios="Apple Push Notification service (APNs).",
                                           android="Firebase Cloud Messaging (FCM).",
                                           huawei="Huawei Push Kit (HMS) — FCM is unavailable.")),
    MobileCapability("deep_links", "Deep links", "Communication", GENERATED,
                     "app://… routes plus platform universal/app links where configured."),
    MobileCapability("sharing", "Sharing", "Communication", GENERATED,
                     "Share content to other apps via the native share sheet."),
    MobileCapability("in_app_email", "Email", "Communication", GENERATED,
                     "Transactional email sent by the backend — not from the device."),

    # Commerce (spec §21, §22)
    MobileCapability("commerce", "Commerce", "Commerce", GENERATED,
                     "Catalogue, cart, checkout and orders over the SAME commerce backend as web."),
    MobileCapability("payments", "Payments", "Commerce", GATED,
                     "Manual/EFT today via the shared engine; card gateways activate when connected. "
                     "Digital goods inside the app may require store billing rules.",
                     platform_notes=_notes(
                         ios="Digital goods may require Apple In-App Purchase.",
                         android="Digital goods may require Google Play Billing.")),
    MobileCapability("subscriptions", "Subscriptions", "Commerce", GENERATED,
                     "Recurring plans billed as real orders through the shared subscription engine."),
    MobileCapability("invoicing", "Invoices & receipts", "Commerce", GENERATED,
                     "Real invoices/receipts for orders, with honest paid/unpaid status."),

    # Analytics (spec §40, §41)
    MobileCapability("analytics", "Analytics", "Analytics", GENERATED,
                     "App opens, sessions, screen views, events and conversions over the real backend."),
    MobileCapability("crash_monitoring", "Crash & error monitoring", "Analytics", GATED,
                     "Crashes, crash-free sessions, error rates and slow screens — activates when a "
                     "monitoring provider is connected; no internal infra is exposed."),

    # Release (spec §23–52) — the whole build/sign/store pipeline is REAL machinery in
    # apps.release, honestly gated on store credentials; nothing here fakes a submission.
    MobileCapability("versioning", "Versioning & channels", "Release", GENERATED,
                     "Version, build number and release channels (dev / testing / staging / production)."),
    MobileCapability("store_metadata", "Store metadata & assets", "Release", GENERATED,
                     "Listing, screenshots, icon and required metadata, validated before submission."),
    MobileCapability("signing", "App signing", "Release", GATED,
                     "Certificates / keystores held as secure references — activates on a connected "
                     "developer account; signing secrets are never exposed.",
                     platform_notes=_notes(ios="Certificates & provisioning via Apple Developer.",
                                           android="Upload/app signing key via Google Play.",
                                           huawei="Signing via Huawei AppGallery Connect.")),
    MobileCapability("store_submission", "Store submission", "Release", GATED,
                     "TestFlight / Play tracks / AppGallery submission and review — activates when the "
                     "store is connected; nothing is submitted without credentials.",
                     platform_notes=_notes(ios="App Store Connect / TestFlight.",
                                           android="Google Play Console tracks.",
                                           huawei="Huawei AppGallery Connect.")),
    MobileCapability("feature_flags", "Feature flags", "Release", GENERATED,
                     "Server-controlled flags to enable/disable features without shipping a binary."),
    MobileCapability("app_updates", "Update strategy", "Release", GENERATED,
                     "Version detection, optional/mandatory updates and minimum supported version."),
]

_BY_ID = {c.id: c for c in _CATALOG}


def get(capability_id: str) -> MobileCapability | None:
    return _BY_ID.get(capability_id)


def all_capabilities() -> list[MobileCapability]:
    return list(_CATALOG)


def by_group() -> list[tuple[str, list[MobileCapability]]]:
    groups: dict[str, list[MobileCapability]] = {}
    for c in _CATALOG:
        groups.setdefault(c.group, []).append(c)
    return [(g, groups[g]) for g in GROUPS if g in groups]


def permission(permission_id: str) -> DevicePermission | None:
    return PERMISSIONS.get(permission_id)


def capability_lines(ids) -> str:
    """Readable "Name — summary" lines for the given capability ids, for an AI prompt."""
    lines = []
    for cid in ids:
        c = get(cid)
        if c:
            lines.append(f"- {c.name} — {c.summary}")
    return "\n".join(lines)


def permission_lines(permission_ids) -> str:
    """Readable "Name — rationale" lines for the given device-permission ids."""
    lines = []
    for pid in permission_ids:
        p = permission(pid)
        if p:
            lines.append(f"- {p.name} — {p.rationale}")
    return "\n".join(lines)
