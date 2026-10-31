"""The actions an automation can perform (spec §10), and their HONEST execution.

Every action does something the platform can really do, and reports its outcome
truthfully:

  - done     : it genuinely happened.
  - skipped  : it was deliberately not done (e.g. a capability isn't configured) —
               never dressed up as success.
  - failed   : it was attempted and errored.

An action that needs infrastructure the project doesn't have (real email delivery)
is *skipped* with a clear reason, never faked. Values are templated from the
trigger's facts with a simple {fact} substitution — no code execution.
"""
from __future__ import annotations

import re

from django.conf import settings

DONE, SKIPPED, FAILED = "done", "skipped", "failed"

_TOKEN = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def render(template: str, facts: dict) -> str:
    """Substitute {fact} tokens from facts; unknown tokens are left blank."""
    facts = facts or {}
    return _TOKEN.sub(lambda m: str(facts.get(m.group(1), "")), template or "")


def _email_configured() -> bool:
    """True only when a real outbound email backend is configured. The console and
    in-memory backends (dev/test) are not real delivery, so email actions are
    honestly skipped there rather than reported as sent."""
    backend = getattr(settings, "EMAIL_BACKEND", "") or ""
    return "smtp" in backend or "anymail" in backend


# --- executors: (project, params, facts, user) -> (outcome, detail) ----------

def _act_notify(project, params, facts, user):
    message = render(params.get("message", ""), facts).strip()
    if not message:
        return FAILED, "No message to send."
    from apps.notifications.alerts import raise_alert
    alert = raise_alert(project, kind="automation",
                        message=message, severity=params.get("severity", "medium"))
    extra = f" (emailed {alert.emailed})" if getattr(alert, "emailed", 0) else ""
    return DONE, f"Alert raised{extra}."


def _act_note(project, params, facts, user):
    from apps.project_context.models import ContextKind
    from apps.project_context.services import ProjectContext
    text = render(params.get("text", ""), facts).strip()
    if not text:
        return FAILED, "No note text."
    ProjectContext(project).add(
        ContextKind.NOTE, title=(params.get("title") or "Automation")[:255],
        content=text, source="automation")
    return DONE, "Note added to project memory."


def _act_open_incident(project, params, facts, user):
    from apps.incidents import service as inc
    title = render(params.get("title", ""), facts).strip()
    if not title:
        return FAILED, "No incident title."
    inc.open_incident(project, title=title, severity=params.get("severity", "medium"),
                      source="automation", user=user)
    return DONE, f"Incident opened: {title}"


def _act_email(project, params, facts, user):
    to = render(params.get("to", ""), facts).strip()
    subject = render(params.get("subject", ""), facts).strip() or f"{project.name} update"
    body = render(params.get("message", ""), facts).strip()
    if not to:
        return FAILED, "No recipient."
    if not _email_configured():
        return SKIPPED, "Email delivery isn't configured — nothing was sent."
    try:
        from apps.notifications.email import send_email
        sent = send_email(subject=subject, to=to, text=body or subject)
    except Exception as exc:  # pragma: no cover - defensive
        return FAILED, f"Email failed: {exc}"[:200]
    return (DONE, f"Email sent to {to}.") if sent else (SKIPPED, "No email sent.")


# key -> {label, executor, needs: [param names for the builder]}
ACTIONS = {
    "notify": {"label": "Raise an alert", "run": _act_notify,
               "params": ["message", "severity"]},
    "note": {"label": "Add a note to project memory", "run": _act_note,
             "params": ["title", "text"]},
    "open_incident": {"label": "Open an incident", "run": _act_open_incident,
                      "params": ["title", "severity"]},
    "email": {"label": "Send an email", "run": _act_email,
              "params": ["to", "subject", "message"]},
}


def is_valid(action_type: str) -> bool:
    return action_type in ACTIONS


def run_action(action_type: str, project, params: dict, facts: dict, user=None):
    spec = ACTIONS.get(action_type)
    if not spec:
        return FAILED, f"Unknown action '{action_type}'."
    try:
        return spec["run"](project, params or {}, facts or {}, user)
    except Exception as exc:  # an action's failure never breaks the run
        return FAILED, str(exc)[:200]


def choices():
    return [(k, v["label"]) for k, v in ACTIONS.items()]
