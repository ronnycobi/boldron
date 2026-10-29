"""AI debugging engine (spec §7).

When a recorded test run FAILS, analyse its real output to find a likely root cause
and affected component, then propose a FIX as a change request that goes through the
normal safe-change pipeline (plan → impact → approve → implement → re-test).

  FAILURE → ERROR ANALYSIS → ROOT CAUSE → AFFECTED COMPONENT → PROPOSE FIX → (change
  engine) IMPLEMENT → TEST → verify

Honesty (spec §7): this NEVER claims an error is fixed. It only diagnoses and
proposes; the fix is a reviewed change, and whether it worked is decided by a fresh
test run (tests_green), not by this module. The analysis is deterministic over the
real log (no fabricated causes); an AI pass may add a plain-language explanation
when a model is available, and is skipped silently otherwise. Customer-safe (§30):
it describes the app's own error, with sandbox paths reduced to file names.
"""
from __future__ import annotations

import re

from apps.testing.models import TestRun, TestRunStatus

# Common failure categories → a plain-language root-cause hint (deterministic).
_CATEGORY_HINTS = {
    "AssertionError": ("assertion", "A test's expected value didn't match the actual result."),
    "ImportError": ("import", "Code imports a module or name that isn't available."),
    "ModuleNotFoundError": ("import", "A required module is missing or misnamed."),
    "SyntaxError": ("syntax", "There's a syntax error in the code."),
    "IndentationError": ("syntax", "The code has an indentation problem."),
    "TypeError": ("type", "A value of the wrong type was used."),
    "AttributeError": ("attribute", "Code accessed an attribute/method that doesn't exist."),
    "KeyError": ("data", "A lookup used a key that isn't present."),
    "NameError": ("name", "Code refers to a name that isn't defined."),
    "ValueError": ("value", "A value was out of the accepted range or format."),
    "TimeoutError": ("timeout", "An operation took too long."),
}


def _basename_paths(text: str) -> str:
    """Reduce absolute sandbox paths to file names (customer-safe)."""
    return re.sub(r'File "([^"]*/)?([^"/]+)"', r'File "\2"', text or "")


def analyze_failure(run: TestRun, *, enrich: bool = False) -> dict | None:
    """A structured diagnosis of a failed run, from its real log. None if the run
    didn't fail (nothing to debug).

    Deterministic and instant by default — safe to call on every page/API read. Pass
    enrich=True to additionally ask a model for a plain-language cause/fix; that makes
    a network call, so it is never on the hot path."""
    if run.status not in (TestRunStatus.FAILED, TestRunStatus.ERROR):
        return None
    log = _basename_paths(run.log or "")

    # Failing test identifiers: unittest "FAIL:/ERROR: test_x (module.Class)".
    failing = re.findall(r"^(?:FAIL|ERROR): (\S+)", log, re.M)[:10]

    # The exception type on the last traceback line (e.g. "AssertionError: ...").
    exc_type, exc_message, category, root_cause = "", "", "unknown", ""
    for m in re.finditer(r"^(\w+Error|\w+Exception): ?(.*)$", log, re.M):
        exc_type, exc_message = m.group(1), m.group(2).strip()
    if exc_type in _CATEGORY_HINTS:
        category, root_cause = _CATEGORY_HINTS[exc_type]
    elif exc_type:
        category, root_cause = "exception", f"The code raised {exc_type}."

    # Where: the last 'File "name", line N' in the traceback.
    location = ""
    files = re.findall(r'File "([^"]+)", line (\d+)', log)
    if files:
        fname, line = files[-1]
        location = f"{fname}:{line}"

    diagnosis = {
        "category": category,
        "exception": exc_type,
        "message": exc_message[:200],
        "failing_tests": failing,
        "location": location,
        "root_cause": root_cause or "The test suite reported a failure; see the log.",
        "log_excerpt": log[-1500:],
        "source": "analysis",
    }
    if enrich:
        _ai_enrich(run, diagnosis)
    return diagnosis


def _ai_enrich(run: TestRun, diagnosis: dict) -> None:
    """Optionally add a plain-language root cause + suggested fix from a model.
    Silently left out when no model is available — never faked."""
    try:
        from apps.ai_providers.base import Message
        from apps.model_router.router import ModelRouter, RoutingRequest, TaskComplexity
        router = ModelRouter()
        system = (
            "You are a debugging assistant. Given a failing test log, reply with ONLY "
            "JSON: {\"root_cause\": one sentence, \"suggested_fix\": one sentence}. "
            "Base it strictly on the log; invent nothing."
        )
        resp = router.complete(
            RoutingRequest(complexity=TaskComplexity.LOW, task_type="debug"),
            messages=[Message(role="user", content=diagnosis["log_excerpt"])],
            system=system, max_tokens=200)
        m = re.search(r"\{.*\}", resp.text, re.S)
        if not m:
            return
        import json
        data = json.loads(m.group(0))
        if data.get("root_cause"):
            diagnosis["root_cause"] = str(data["root_cause"])[:300]
            diagnosis["source"] = resp.model
        if data.get("suggested_fix"):
            diagnosis["suggested_fix"] = str(data["suggested_fix"])[:300]
    except Exception:
        return  # honest: no AI enrichment, deterministic analysis stands


def propose_fix(run: TestRun, *, user=None):
    """Create a change request to fix a failed run, entering the safe-change pipeline.
    Returns the ChangeRequest. Never implements it and never claims the run is fixed —
    the fix is reviewed, implemented, then verified by a fresh test run."""
    from apps.changes import service as changes
    if run.status not in (TestRunStatus.FAILED, TestRunStatus.ERROR):
        raise ValueError("Only a failed test run can have a fix proposed.")
    d = analyze_failure(run) or {}
    tests = ", ".join(d.get("failing_tests", [])[:3])
    parts = ["Fix the failing test run."]
    if tests:
        parts.append(f"Failing: {tests}.")
    if d.get("root_cause"):
        parts.append(d["root_cause"])
    if d.get("location"):
        parts.append(f"Starts around {d['location']}.")
    if d.get("suggested_fix"):
        parts.append(f"Suggested: {d['suggested_fix']}")
    description = " ".join(parts)

    change = changes.create_change(run.project, description, user)
    try:
        changes.build_plan(change)   # plan + impact + approval gate (safe-change engine)
    except Exception:
        pass  # a missing model leaves an un-planned change; it's still a real request
    # Link the originating run to the change it spawned, for traceability.
    run.change = change
    run.save(update_fields=["change"])
    return change
