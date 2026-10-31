"""The events an automation can react to (spec §10).

Only events the platform genuinely emits are listed — every trigger here is wired
to a real emitter (see apps that call `engine.fire`). A trigger nothing can raise
would be dishonest, so none is offered. Each entry documents the facts the event
carries, which an automation's conditions and action templates can use.
"""
from __future__ import annotations

# key -> {label, description, facts: [names]}
TRIGGERS = {
    "manual": {
        "label": "Run manually",
        "description": "Run on demand — also used to test an automation.",
        "facts": [],
    },
    "incident.opened": {
        "label": "Incident opened",
        "description": "An operational incident is opened for the project.",
        "facts": ["title", "severity", "source"],
    },
    "incident.resolved": {
        "label": "Incident resolved",
        "description": "An incident is marked resolved.",
        "facts": ["title", "severity"],
    },
    "deploy.succeeded": {
        "label": "Deploy succeeded",
        "description": "A deployment finishes successfully.",
        "facts": ["environment", "is_production"],
    },
    "deploy.failed": {
        "label": "Deploy failed",
        "description": "A deployment fails.",
        "facts": ["environment", "is_production"],
    },
    "tests.failed": {
        "label": "Tests failed",
        "description": "A test run does not pass.",
        "facts": ["failures", "errors", "ran"],
    },
    "security.blocked": {
        "label": "Security scan blocked",
        "description": "A security scan finds a high-severity issue.",
        "facts": ["high", "medium", "low"],
    },
}


def is_valid(trigger: str) -> bool:
    return trigger in TRIGGERS


def choices():
    return [(k, v["label"]) for k, v in TRIGGERS.items()]
