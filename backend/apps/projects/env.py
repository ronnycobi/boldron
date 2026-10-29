"""Project environment variables — per environment, stored and (really) injected.

The values set here are genuinely consumed: apps.preview_runner merges
env_for_project() into the environment of the running preview process, so a var set
in settings actually reaches the customer's app. Each variable belongs to one
environment (development / staging / production), so the same key can differ per
environment (spec §11).

Secret-flagged values are write-only over the API/UI (masked on read) AND encrypted
at rest (apps.projects.secrets_crypto); plain values are config, shown so they can be
edited. A secret's plaintext is only ever decrypted server-side for injection into
the run — never returned to the UI, the API or the mobile app.
"""
from __future__ import annotations

import re

from apps.projects.models import EnvVar
from apps.projects.secrets_crypto import decrypt_secret, encrypt_secret

_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MASK = "••••••••"

# The standard environments every project has (spec §11).
ENVIRONMENTS = [e for e, _ in EnvVar.ENVIRONMENTS]
_ENV_LABELS = dict(EnvVar.ENVIRONMENTS)
DEFAULT_ENVIRONMENT = "development"


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


def validate_environment(environment: str) -> str:
    environment = (environment or DEFAULT_ENVIRONMENT).strip().lower()
    if environment not in ENVIRONMENTS:
        raise EnvVarError(f"Unknown environment '{environment}'.")
    return environment


def environments() -> list[dict]:
    return [{"id": e, "label": _ENV_LABELS[e]} for e in ENVIRONMENTS]


def set_var(project, key: str, value: str, *, is_secret: bool = False,
            environment: str = DEFAULT_ENVIRONMENT) -> EnvVar:
    """Create or update a variable in one environment. Secrets are encrypted at rest."""
    key = validate_key(key)
    environment = validate_environment(environment)
    is_secret = bool(is_secret)
    stored = encrypt_secret(value or "") if is_secret else (value or "")
    var, _ = EnvVar.objects.update_or_create(
        project=project, environment=environment, key=key,
        defaults={"value": stored, "is_secret": is_secret},
    )
    return var


def delete_var(project, var_id) -> bool:
    deleted, _ = EnvVar.objects.filter(project=project, id=var_id).delete()
    return bool(deleted)


def list_vars(project, environment: str | None = None):
    qs = project.env_vars.all()
    if environment is not None:
        qs = qs.filter(environment=validate_environment(environment))
    return list(qs)


def _plain(var: EnvVar) -> str:
    """The real value (secrets decrypted) — for injection only, never for display."""
    return decrypt_secret(var.value) if var.is_secret else var.value


def env_for_project(project, environment: str = DEFAULT_ENVIRONMENT) -> dict[str, str]:
    """{KEY: value} for injection into the project's run/preview process, for one
    environment. Secret values are decrypted here (server-side) for the real run."""
    environment = validate_environment(environment)
    return {v.key: _plain(v) for v in project.env_vars.filter(environment=environment)}


def public_dict(var: EnvVar) -> dict:
    """Serialised form for API/UI reads. A secret's value is NEVER returned (not even
    decrypted) — only whether it is set — so secrets can't be read back."""
    return {
        "id": var.id,
        "key": var.key,
        "environment": var.environment,
        "is_secret": var.is_secret,
        "value": MASK if var.is_secret else var.value,
        "has_value": bool(var.value),
    }
