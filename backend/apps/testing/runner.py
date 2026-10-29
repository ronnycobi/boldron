"""Test-run engine (spec §8) — run a project's tests for real and record the result.

Reuses the genuine executor (apps.codegen.run_repo_tests, which runs the repo in the
sandbox and returns real counts). This module turns one run into a persistent
TestRun ledger entry and provides the deploy gate (`tests_green`).

Nothing here fabricates a result: a run with nothing to execute is recorded as
SKIPPED (not passed), an execution error as ERROR, and the gate treats both as
"not green" — you can't claim tests passed if they did not actually pass.
"""
from __future__ import annotations

from django.utils import timezone

from apps.audit.service import record as audit
from apps.testing.models import TestRun, TestRunStatus


def _apply_result(run: TestRun, result: dict) -> TestRun:
    """Map a real run_repo_tests result onto the ledger entry, honestly."""
    passed = result.get("passed")
    run.ran = int(result.get("ran", 0) or 0)
    run.failures = int(result.get("failures", 0) or 0)
    run.errors = int(result.get("errors", 0) or 0)
    run.note = (result.get("note", "") or "")[:300]
    if passed is None:
        run.status = TestRunStatus.SKIPPED
    elif passed:
        run.status = TestRunStatus.PASSED
    else:
        run.status = TestRunStatus.FAILED
    run.finished_at = timezone.now()
    run.save(update_fields=["ran", "failures", "errors", "note", "status", "finished_at"])
    return run


def run_project_tests(project, *, change=None, trigger="manual", user=None,
                      executor=None) -> TestRun:
    """Run the project's test suite and record a TestRun with the REAL outcome.

    `executor(project) -> dict` defaults to the genuine sandbox test runner; it is
    injectable only so the behaviour can be tested deterministically."""
    if executor is None:
        from apps.codegen.service import run_repo_tests as executor
    run = TestRun.objects.create(
        project=project, change=change, trigger=trigger, created_by=user,
        status=TestRunStatus.RUNNING)
    try:
        result = executor(project)
    except Exception as exc:                       # the run itself broke — honest ERROR
        run.status = TestRunStatus.ERROR
        run.note = str(exc)[:300]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "note", "finished_at"])
    else:
        _apply_result(run, result if isinstance(result, dict) else {})
    audit("tests.run", actor=user, organization=project.organization,
          target=f"project:{project.id}", summary=f"{run.status}: {run.summary}")
    return run


def latest_run(project) -> TestRun | None:
    return project.test_runs.first()


def tests_green(project) -> bool:
    """True only when the latest recorded run actually PASSED. A skipped/errored/
    never-run project is not green — the deploy gate relies on this being honest."""
    run = latest_run(project)
    return bool(run and run.passed)
