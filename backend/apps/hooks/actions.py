"""Hook action handlers — each returns (status, detail) where status is pass/fail/skip.

They reuse real the platform services (the test runner, the security scanner). None
fabricates a result: if there's nothing to check, the handler returns 'skip'.
"""
from __future__ import annotations


def run_tests(project, config) -> tuple[str, str]:
    # Run through the ledger so every pre-deploy test run is recorded with its real
    # outcome (apps.testing.runner reuses the same sandbox executor).
    from apps.testing.models import TestRunStatus
    from apps.testing.runner import run_project_tests
    run = run_project_tests(project, trigger="pre_deploy")
    if run.status == TestRunStatus.SKIPPED:
        return "skip", run.summary
    if run.status == TestRunStatus.PASSED:
        return "pass", run.summary
    return "fail", run.summary   # FAILED or ERROR both block the deploy


def security_scan(project, config) -> tuple[str, str]:
    # Scan through the ledger so every pre-deploy scan is recorded with its real
    # findings (apps.security.ledger reuses the same scanner).
    from apps.security.ledger import run_scan
    from apps.security.models import SecurityScanStatus
    scan = run_scan(project, trigger="pre_deploy")
    if scan.status == SecurityScanStatus.SKIPPED:
        return "skip", scan.summary
    if scan.status == SecurityScanStatus.BLOCKED:
        return "fail", scan.summary          # a HIGH finding blocks the deploy
    if scan.status == SecurityScanStatus.ERROR:
        return "fail", scan.summary
    return "pass", scan.summary              # clean or non-blocking findings


def manual_gate(project, config) -> tuple[str, str]:
    # A hard human sign-off gate: fails (blocks) until someone explicitly clears it.
    if config and config.get("cleared"):
        return "pass", "manually cleared"
    return "fail", config.get("message", "awaiting manual sign-off") if config else "awaiting manual sign-off"


ACTIONS = {
    "run_tests": run_tests,
    "security_scan": security_scan,
    "manual_gate": manual_gate,
}
