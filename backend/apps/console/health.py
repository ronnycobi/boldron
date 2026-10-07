"""System health checks for the Control Center — honest, live probes only.

Each check actually verifies something (a DB query, provider availability, the
sandbox, a writable workspaces dir). Anything we can't genuinely probe reports
"not monitored" rather than a green light we didn't earn.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.db import connection


def _check(name, fn):
    try:
        ok, detail = fn()
        return {"name": name, "status": "ok" if ok else "down", "detail": detail}
    except Exception as exc:  # a failing probe is a real signal, not a crash
        return {"name": name, "status": "down", "detail": str(exc)[:120]}


def _database():
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    return True, connection.vendor


def _sandbox():
    from apps.build_sandbox.service import get_sandbox
    get_sandbox()
    return True, "ready"


def _storage():
    root = settings.BOLDRON_WORKSPACES_ROOT
    os.makedirs(root, exist_ok=True)
    return os.access(root, os.W_OK), str(root)


def _ai_check() -> dict:
    # AI gets its own status: "ok" when a real model is connected, otherwise
    # "unknown" (demo mode) — not "down", since the offline stub still serves.
    from apps.ai_providers.registry import generation_status
    s = generation_status()
    return {"name": "AI model", "status": "ok" if s["live"] else "unknown",
            "detail": s["message"]}


def system_health() -> list[dict]:
    checks = [
        _check("Database", _database),
        _ai_check(),
        _check("Build sandbox", _sandbox),
        _check("Storage", _storage),
    ]
    # Honest placeholders for things without a real probe in this environment.
    checks += [
        {"name": "Deployment", "status": "unknown", "detail": "no live target connected"},
        {"name": "Queue / workers", "status": "unknown", "detail": "synchronous — no queue yet"},
    ]
    return checks


def all_ok(checks) -> bool:
    return all(c["status"] != "down" for c in checks)
