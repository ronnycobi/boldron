"""Project environment variables — store and (really) inject.

The values set here are genuinely consumed: apps.preview_runner merges
env_for_project() into the environment of the running preview process, so a var
set in settings actually reaches the customer's app. Secret-flagged values are
write-only over the API/UI (masked on read); plain values are shown so they can
be edited.
"""
from __future__ import annotations

import re

from apps.projects.models import EnvVar

_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MASK = "••••••••"


class EnvVarError(Exception):
    pass


def normalize_key(key: str) -> str:
    return (key or "").strip()


def validate_key(key: str) -> str:
    key = normalize_key(key)
    if not _KEY_RE.match(key):
        raise EnvVarError(
            "Keys must be UPPER_SNAKE_CASE: letters, digits and underscores, "
            "not starting with a digit."
        )
    return key


def set_var(project, key: str, value: str, *, is_secret: bool = False) -> EnvVar:
    """Create or update a variable. Returns the stored EnvVar."""
    key = validate_key(key)
    var, _ = EnvVar.objects.update_or_create(
        project=project, key=key,
        defaults={"value": value or "", "is_secret": bool(is_secret)},
    )
    return var


def delete_var(project, var_id) -> bool:
    deleted, _ = EnvVar.objects.filter(project=project, id=var_id).delete()
    return bool(deleted)


def list_vars(project):
    return list(project.env_vars.all())


def env_for_project(project) -> dict[str, str]:
    """{KEY: value} for injection into the project's run/preview process."""
    return {v.key: v.value for v in project.env_vars.all()}


def public_dict(var: EnvVar) -> dict:
    """Serialised form for API/UI reads. A secret's value is never returned —
    only whether it is set — so secrets can't be read back."""
    return {
        "id": var.id,
        "key": var.key,
        "is_secret": var.is_secret,
        "value": MASK if var.is_secret else var.value,
        "has_value": bool(var.value),
    }
