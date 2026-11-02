"""License-tracking service (spec §12): import dependencies, classify licenses,
produce a license report and an attribution notice — honestly flagging anything
that needs review rather than declaring the project legally safe."""
from __future__ import annotations

from django.db import IntegrityError

from apps.audit.service import record as audit
from apps.licenses.classifier import classify
from apps.licenses.models import Dependency
from apps.project_context.models import ContextKind


class LicenseError(Exception):
    pass


def record_dependency(project, *, package, version="", license="", source="",
                      dependency_type="runtime", user=None) -> Dependency:
    package = (package or "").strip()
    if not package:
        raise LicenseError("A dependency needs a package name.")
    dep, _ = Dependency.objects.update_or_create(
        project=project, package=package[:200],
        defaults={"version": version[:60], "license": license[:120],
                  "source": source[:60], "dependency_type": dependency_type})
    return dep


def import_from_context(project) -> int:
    """Seed dependency rows from the names captured during import (license unknown
    until recorded). Idempotent."""
    entry = project.context_entries.filter(
        kind=ContextKind.DEPENDENCY, key="dependencies").first()
    if not entry:
        return 0
    names = (entry.data or {}).get("dependencies") or []
    created = 0
    for name in names:
        name = str(name).strip()
        if not name or Dependency.objects.filter(project=project, package=name[:200]).exists():
            continue
        Dependency.objects.create(project=project, package=name[:200])
        created += 1
    if created:
        audit("licenses.import", organization=project.organization,
              target=f"project:{project.id}", summary=f"{created} dependencies")
    return created


def report(project) -> dict:
    """Per-dependency license classification + an honest summary. `legally_safe` is
    never asserted — instead we count what needs review."""
    deps = list(project.dependencies.all())
    rows, flags = [], {"ok": 0, "review": 0, "unknown": 0}
    for d in deps:
        c = classify(d.license)
        flags[c["flag"]] = flags.get(c["flag"], 0) + 1
        rows.append({"package": d.package, "version": d.version,
                     "license": d.license or "(unknown)", "category": c["category"],
                     "flag": c["flag"], "source": d.source})
    needs_review = flags["review"] + flags["unknown"]
    return {
        "dependencies": rows,
        "total": len(deps),
        "flags": flags,
        "needs_review": needs_review,
        "note": ("Some dependencies use copyleft licenses or have no license "
                 "recorded — review their obligations with legal counsel. This is "
                 "not a determination that the project is legally safe."
                 if needs_review else
                 "No dependencies recorded." if not deps else
                 "All recorded dependencies use permissive licenses. This is not a "
                 "legal determination — confirm obligations before distribution."),
    }


def attribution(project) -> str:
    """A simple third-party attribution/NOTICE text from recorded dependencies."""
    lines = [f"Third-party notices for {project.name}", ""]
    for d in project.dependencies.all():
        lic = d.license or "license unknown"
        ver = f" {d.version}" if d.version else ""
        lines.append(f"- {d.package}{ver} — {lic}")
    if len(lines) == 2:
        lines.append("(No dependencies recorded.)")
    return "\n".join(lines)


def summary(project) -> dict:
    rep = report(project)
    return {"total": rep["total"], "needs_review": rep["needs_review"]}
