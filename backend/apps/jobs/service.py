"""Job runner + handler registry.

enqueue() creates a Job (queued) and runs its handler on a worker thread (inline
under tests for determinism, matching apps.projects.builds). The handler receives
the Job and does real work, updating progress; whatever dict it returns is stored
as the result. Status transitions are honest: running on start, completed only
when the handler returns, failed with the real exception message otherwise.
"""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.jobs.models import Job

# kind -> (handler, friendly label). Register real handlers only.
_HANDLERS: dict[str, tuple] = {}


class JobError(Exception):
    pass


def register(kind: str, label: str):
    def _wrap(fn):
        _HANDLERS[kind] = (fn, label)
        return fn
    return _wrap


def kinds() -> list[dict]:
    return [{"kind": k, "label": label} for k, (fn, label) in _HANDLERS.items()]


def enqueue(kind: str, *, organization, project=None, created_by=None,
            params: dict | None = None) -> Job:
    """Create and start a job. The handler runs off the request thread."""
    if kind not in _HANDLERS:
        raise JobError(f"Unknown job type '{kind}'.")
    _, label = _HANDLERS[kind]
    job = Job.objects.create(
        organization=organization, project=project, created_by=created_by,
        kind=kind, label=label, params=params or {}, status=Job.QUEUED)
    _dispatch(job)
    return job


def _dispatch(job: Job) -> None:
    if getattr(settings, "RUNNING_TESTS", False):
        _run(job.id)
        return
    import threading

    from django.db import connection

    def _bg():
        try:
            _run(job.id)
        finally:
            connection.close()  # don't leak this thread's DB connection

    threading.Thread(target=_bg, daemon=True).start()


def _run(job_id: int) -> None:
    job = Job.objects.filter(pk=job_id).first()
    if job is None or job.status != Job.QUEUED:
        return
    handler = _HANDLERS[job.kind][0]
    job.status = Job.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    try:
        result = handler(job) or {}
        job.result = result
        job.status = Job.COMPLETED
        job.progress = 100
    except Exception as exc:  # honest failure — never a fake "completed"
        job.status = Job.FAILED
        job.error = str(exc)[:500]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "progress", "error", "finished_at"])


def public_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "label": job.label,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "has_result": bool(job.result),
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# Import the real handlers so they register on app load.
def load_handlers():  # called from apps.ready via a light import
    from apps.jobs import handlers  # noqa: F401
