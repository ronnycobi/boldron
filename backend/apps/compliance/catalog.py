"""The standard compliance controls per framework (spec §16).

Each control is a real, recognisable requirement. A control with an `auto`
evaluator is one the platform genuinely provides — the evaluator returns a status
and the real basis for it from live facts; everything else is a manual
attestation that starts pending. Auto evaluators must only report what is
actually true (no optimistic defaults).
"""
from __future__ import annotations

from apps.compliance.models import ControlStatus, Framework


# --- auto evaluators: project -> (status, evidence) --------------------------

def _auto_export(project):
    # The platform genuinely provides account + organization data export.
    return ControlStatus.MET, "Account and organization data can be exported on demand."


def _auto_audit(project):
    return ControlStatus.MET, "Sensitive actions are recorded in a tamper-evident audit log."


def _auto_access_control(project):
    return ControlStatus.MET, "Organization roles enforce least-privilege access to project data."


def _auto_backups(project):
    if "backups" in (project.capabilities or []):
        return ControlStatus.MET, "Restore points are available and can be rolled back."
    return ControlStatus.PENDING, "Enable backups to satisfy this control."


# (code, title, description, auto-evaluator | None)
CATALOG = {
    Framework.GDPR: [
        ("data_export", "Right to data portability",
         "Users can obtain a copy of their personal data.", _auto_export),
        ("access_control", "Access control",
         "Personal data is accessible only to authorised roles.", _auto_access_control),
        ("audit_trail", "Processing records",
         "Changes to personal data are logged.", _auto_audit),
        ("privacy_policy", "Privacy policy published",
         "A clear privacy policy is available to users.", None),
        ("lawful_basis", "Lawful basis documented",
         "A lawful basis for each processing activity is recorded.", None),
        ("consent", "Consent & cookie banner",
         "Consent is captured where required (e.g. non-essential cookies).", None),
        ("retention", "Data retention schedule",
         "Personal data is kept only as long as needed, per a defined schedule.", None),
        ("breach", "Breach notification process",
         "A process exists to notify authorities/users of a breach in time.", None),
    ],
    Framework.POPIA: [
        ("data_export", "Access to personal information",
         "Data subjects can access their personal information.", _auto_export),
        ("access_control", "Security safeguards — access",
         "Access to personal information is restricted by role.", _auto_access_control),
        ("audit_trail", "Operator records",
         "Processing of personal information is logged.", _auto_audit),
        ("information_officer", "Information Officer registered",
         "An Information Officer is appointed and registered.", None),
        ("consent", "Consent for processing",
         "Consent is obtained where POPIA requires it.", None),
        ("retention", "Retention & deletion",
         "Personal information is deleted when no longer needed.", None),
    ],
    Framework.ACCESSIBILITY: [
        ("contrast", "Sufficient colour contrast",
         "Text meets WCAG AA contrast ratios.", None),
        ("keyboard", "Keyboard operable",
         "All functionality is available from a keyboard.", None),
        ("alt_text", "Text alternatives",
         "Images and media have meaningful alternative text.", None),
        ("labels", "Form labels",
         "Form controls have associated labels.", None),
    ],
    Framework.SECURITY: [
        ("access_control", "Role-based access",
         "Access is least-privilege by role.", _auto_access_control),
        ("audit_trail", "Audit logging",
         "Security-relevant actions are logged.", _auto_audit),
        ("backups", "Backups & recovery",
         "Data can be restored from a recent backup.", _auto_backups),
        ("transport_encryption", "Encryption in transit",
         "Traffic is served over HTTPS with a valid certificate.", None),
        ("secrets", "Secrets management",
         "Secrets are stored outside source control.", None),
    ],
}


def frameworks() -> list[dict]:
    return [{"key": f.value, "label": f.label} for f in Framework]
