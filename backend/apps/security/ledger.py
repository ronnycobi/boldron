"""Security-scan engine (spec §8) — scan a project's code for real and record it.

Reuses the genuine scanner (apps.security.scanner, offline pattern detection for
secrets, injection, XSS, SQLi, unsafe config). This module turns one scan into a
persistent SecurityScan + SecurityFinding ledger entry and provides the deploy gate
(`security_ok`).

Honesty: a scan with no code is recorded as SKIPPED (not clean), and the gate treats
a high-severity finding as blocking — nothing is reported safe that wasn't scanned.
"""
from __future__ import annotations

from apps.audit.service import record as audit
from apps.security.models import SecurityFinding, SecurityScan, SecurityScanStatus
from apps.security.scanner import Severity, scan_files, summarize

# Binary / non-source files we don't scan.
_SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
             ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mp3", ".wasm")
_MAX_STORED = 200   # cap stored findings per scan (the counts are always exact)


def _collect_files(project) -> dict[str, str] | None:
    from apps.repositories.service import repo_for_project
    repo = repo_for_project(project)
    if not repo.is_initialized:
        return None
    files = {}
    for rel in repo.list_files():
        if rel.lower().endswith(_SKIP_EXT):
            continue
        try:
            files[rel] = (repo.path / rel).read_text()
        except (OSError, UnicodeDecodeError):
            continue
    return files


def run_scan(project, *, trigger="manual", user=None, collector=None) -> SecurityScan:
    """Scan the project's code and record a SecurityScan with the REAL findings.

    `collector(project) -> dict|None` defaults to reading the repo; it is injectable
    only so the behaviour can be tested deterministically."""
    collector = collector or _collect_files
    scan = SecurityScan.objects.create(project=project, trigger=trigger, created_by=user)
    try:
        files = collector(project)
    except Exception as exc:
        scan.status = SecurityScanStatus.ERROR
        scan.note = str(exc)[:300]
        scan.save(update_fields=["status", "note"])
        return scan

    if not files:
        scan.status = SecurityScanStatus.SKIPPED
        scan.note = "no repository" if files is None else "no code to scan"
        scan.save(update_fields=["status", "note"])
    else:
        findings = scan_files(files)
        counts = summarize(findings)
        scan.high = counts.get(Severity.HIGH, 0)
        scan.medium = counts.get(Severity.MEDIUM, 0)
        scan.low = counts.get(Severity.LOW, 0)
        scan.files_scanned = len(files)
        if scan.high:
            scan.status = SecurityScanStatus.BLOCKED
        elif scan.medium or scan.low:
            scan.status = SecurityScanStatus.FINDINGS
        else:
            scan.status = SecurityScanStatus.CLEAN
        scan.save(update_fields=["high", "medium", "low", "files_scanned", "status"])
        SecurityFinding.objects.bulk_create([
            SecurityFinding(scan=scan, severity=f.severity, category=f.category,
                            message=f.message[:300], path=f.path[:500], line=f.line)
            for f in findings[:_MAX_STORED]
        ])
    audit("security.scan", actor=user, organization=project.organization,
          target=f"project:{project.id}", summary=f"{scan.status}: {scan.summary}")
    if scan.status == SecurityScanStatus.BLOCKED:
        from apps.automations.engine import fire_safe
        fire_safe(project, "security.blocked",
                  {"high": scan.high, "medium": scan.medium, "low": scan.low},
                  user=user)
    return scan


def latest_scan(project) -> SecurityScan | None:
    return project.security_scans.first()


def security_ok(project) -> bool:
    """True when the latest scan found no high-severity issue. A never-scanned project
    is not ok (the deploy gate runs a fresh scan anyway); a skipped scan (no code) is
    ok — there was nothing to block on."""
    scan = latest_scan(project)
    if scan is None:
        return False
    return scan.high == 0 and scan.status != SecurityScanStatus.ERROR
