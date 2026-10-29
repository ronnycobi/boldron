"""The Capability Platform — the building blocks an app can be given.

A customer describes an outcome ("a CRM for my construction company"); the platform
infers the capabilities that outcome needs (auth, database, email, …) instead of
making them configure each one. This registry is the catalogue, grouped, with an
HONEST status per capability:

  - "available"  : the platform genuinely provides or builds this today.
  - "planned"    : on the roadmap; not offered yet.

Status is the guardrail behind the product principle "market only what we
actually provide" — marketing and inference must never present a planned
capability as if it were live.
"""
from __future__ import annotations

from dataclasses import dataclass

AVAILABLE = "available"
PLANNED = "planned"


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    group: str
    status: str
    description: str

    @property
    def is_available(self) -> bool:
        return self.status == AVAILABLE


# Honest statuses as of today: authentication/users/roles, relational database,
# APIs, transactional email (notifications), basic search, dashboards, code
# review + security scan, deploy/preview, export, and Git connect are real.
# Payments, storage, SMS, jobs, analytics, monitoring, multi-currency, tax, SSO,
# and most third-party integrations are on the roadmap.
_CATALOG = [
    # Application
    Capability("auth", "Authentication", "Application", AVAILABLE, "Sign-up, login, password reset."),
    Capability("users", "Users", "Application", AVAILABLE, "User accounts and profiles."),
    Capability("roles", "Roles & permissions", "Application", AVAILABLE, "Org roles and access control."),
    Capability("database", "Database", "Application", AVAILABLE, "Structured data and relationships."),
    Capability("api", "APIs", "Application", AVAILABLE, "HTTP APIs for your data."),
    Capability("search", "Search", "Application", AVAILABLE, "Find records across your app."),
    Capability("dashboard", "Dashboards", "Application", AVAILABLE, "Metrics and overviews."),
    Capability("email", "Email", "Application", AVAILABLE, "Transactional and notification email."),
    Capability("files", "File storage", "Application", AVAILABLE, "Private and public uploads, images, documents, with thumbnails."),
    Capability("sms", "SMS", "Application", PLANNED, "Text-message notifications."),
    Capability("jobs", "Background jobs", "Application", AVAILABLE, "Long-running work (reports, exports, batches) runs off-request with real queued/running/done status."),
    # Business
    Capability("crm", "CRM", "Business", AVAILABLE, "Contacts, leads, deals, activities."),
    Capability("payments", "Payments", "Business", AVAILABLE, "Checkout, manual/EFT payments and refunds today; card gateways (Stripe, PayFast) activate when connected."),
    Capability("subscriptions", "Subscriptions", "Business", AVAILABLE,
               "Recurring plans billed every interval. Each cycle is a real, payable, invoiceable "
               "order; the merchant confirms manual/EFT renewals today, and card auto-renewal "
               "activates when a gateway is connected."),
    Capability("invoicing", "Invoicing", "Business", AVAILABLE, "Real invoices and receipts generated from your orders — printable HTML and PDF, with honest paid/unpaid status."),
    Capability("tax", "Tax", "Business", AVAILABLE, "VAT/sales-tax rates applied deterministically at checkout and itemised on invoices."),
    Capability("currency", "Multi-currency", "Business", AVAILABLE,
               "Format prices per currency and convert deterministically with the rates you store; "
               "revenue reports group by currency. Automatic live FX rates activate when a feed is connected."),
    Capability("ecommerce", "E-commerce", "Business", AVAILABLE, "Products, cart, orders."),
    # Growth
    Capability("analytics", "Analytics", "Growth", AVAILABLE, "Real visitors, page views, traffic sources, conversions and (for stores) revenue."),
    Capability("seo", "SEO", "Growth", AVAILABLE, "Titles, meta, canonical, Open Graph, structured data, sitemap.xml and robots.txt — generated from your site."),
    Capability("forms", "Forms", "Growth", AVAILABLE, "Capture input and leads."),
    Capability("campaigns", "Email campaigns", "Growth", AVAILABLE,
               "Send marketing email to the contacts your site collected (leads + customers) over "
               "the real email engine, with honest per-recipient sent/failed results."),
    # Infrastructure
    Capability("hosting", "Hosting", "Infrastructure", AVAILABLE, "Preview and deploy your app."),
    Capability("mobile_publishing", "App store publishing", "Infrastructure", AVAILABLE,
               "Prepare mobile releases for Google Play, App Store and AppGallery — store listing, "
               "screenshots, signing references, readiness checks and approvals. Live submission "
               "activates when you connect your store credentials; nothing is submitted without them."),
    Capability("domains", "Custom domains", "Infrastructure", AVAILABLE,
               "Connect your own domain and verify ownership with real DNS checks; the verified "
               "domain serves your site. Automatic SSL activates once the domain is routed to live hosting."),
    Capability("backups", "Backups", "Infrastructure", AVAILABLE, "Create restore points and roll back."),
    Capability("environments", "Environments", "Infrastructure", AVAILABLE, "Dev/staging workspaces."),
    Capability("monitoring", "Monitoring", "Infrastructure", AVAILABLE,
               "Real health probes of the site we host — uptime %, response time and incidents. "
               "Remote-server metrics and continuous external probing activate with a connected probe network."),
    # Cross-cutting
    Capability("security", "Security", "Protect", AVAILABLE, "Secret + injection scanning on every change."),
    Capability("audit", "Audit log", "Protect", AVAILABLE, "A record of who changed what."),
    Capability("export", "Export / no lock-in", "Protect", AVAILABLE, "Download your code anytime."),
    Capability("ai", "AI features", "Growth", PLANNED, "Chatbots and document Q&A in your app."),
    # Integrations
    Capability("git", "GitHub / GitLab", "Integrations", AVAILABLE, "Import and connect repositories."),
    Capability("google", "Google Workspace", "Integrations", PLANNED, "Sign-in and data."),
    Capability("slack", "Slack", "Integrations", PLANNED, "Notifications and actions."),
    Capability("whatsapp", "WhatsApp", "Integrations", PLANNED, "Messaging."),
    Capability("stripe", "Stripe", "Integrations", PLANNED, "Card payments."),
    Capability("payfast", "PayFast", "Integrations", PLANNED, "South African payments."),
]

_BY_ID = {c.id: c for c in _CATALOG}
_GROUP_ORDER = ["Application", "Business", "Growth", "Infrastructure", "Protect", "Integrations"]


def get(capability_id: str) -> Capability | None:
    return _BY_ID.get(capability_id)


def all_capabilities() -> list[Capability]:
    return list(_CATALOG)


def by_group() -> list[tuple[str, list[Capability]]]:
    groups: dict[str, list[Capability]] = {}
    for c in _CATALOG:
        groups.setdefault(c.group, []).append(c)
    return [(g, groups[g]) for g in _GROUP_ORDER if g in groups]
