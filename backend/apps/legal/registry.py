"""The legal document-type registry and jurisdictions (spec §4, §5).

A central, EXTENSIBLE catalogue: new document types and jurisdictions can be added
here (or registered at runtime) without touching the engine. Nothing in the engine
hard-codes a specific document — it works off whatever types are registered.
"""
from __future__ import annotations

# code -> human label. Add new types here; the engine treats them uniformly.
DOCUMENT_TYPES: dict[str, str] = {
    "terms_of_service": "Terms of Service",
    "privacy_policy": "Privacy Policy",
    "cookie_policy": "Cookie Policy",
    "acceptable_use_policy": "Acceptable Use Policy",
    "ai_terms": "AI Terms",
    "ai_usage_policy": "AI Usage Policy",
    "ip_policy": "Intellectual Property Policy",
    "copyright_policy": "Copyright / DMCA Policy",
    "security_policy": "Security Policy",
    "responsible_disclosure": "Responsible Disclosure Policy",
    "dpa": "Data Processing Agreement",
    "dpa_addendum": "Data Protection Addendum",
    "subprocessor_policy": "Subprocessor Policy",
    "data_retention_policy": "Data Retention Policy",
    "data_deletion_policy": "Data Deletion Policy",
    "data_export_policy": "Data Export Policy",
    "billing_terms": "Billing Terms",
    "refund_policy": "Refund Policy",
    "cancellation_policy": "Cancellation Policy",
    "free_trial_terms": "Free Trial Terms",
    "subscription_terms": "Subscription Terms",
    "usage_terms": "Usage / Credit Terms",
    "marketplace_terms": "Marketplace Terms",
    "api_terms": "Developer / API Terms",
    "integration_terms": "Integration Terms",
    "mobile_terms": "Mobile Application Terms",
    "reseller_terms": "Reseller / White-label Terms",
    "enterprise_terms": "Enterprise Terms",
    "sla": "Service Level Agreement",
    "support_policy": "Support Policy",
    "beta_terms": "Beta / Early Access Terms",
    "community_guidelines": "Community Guidelines",
    "affiliate_terms": "Affiliate / Referral Terms",
    "export_compliance": "Export / Sanctions Policy",
    "transparency_report": "Transparency Report",
}

# Jurisdictions a document can target. GLOBAL is the fallback for every user.
JURISDICTIONS: dict[str, str] = {
    "global": "Global",
    "south_africa": "South Africa",
    "eu_eea": "EU / EEA",
    "united_kingdom": "United Kingdom",
    "united_states": "United States",
    "canada": "Canada",
    "australia": "Australia",
    "other": "Other",
}


def register_document_type(code: str, label: str) -> None:
    """Register a new document type at runtime (keeps the engine open-ended)."""
    DOCUMENT_TYPES[code] = label


def is_valid_type(code: str) -> bool:
    return code in DOCUMENT_TYPES


def is_valid_jurisdiction(code: str) -> bool:
    return code in JURISDICTIONS


def type_label(code: str) -> str:
    return DOCUMENT_TYPES.get(code, code)
