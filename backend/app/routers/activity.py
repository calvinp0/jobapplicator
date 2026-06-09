from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ClaudeRun, Job, JobCapture
from ..schemas import ActivityItemRead, ActivityRead, ActivitySummaryRead

router = APIRouter(prefix="/activity", tags=["activity"])


# Run lifecycle buckets. The actual ``ClaudeRun.status`` vocabulary today is
# ``created / running / completed / failed / imported`` (see
# ``models.CLAUDE_RUN_STATUSES``); the extra synonyms are listed so a future
# worker that emits e.g. ``queued`` / ``error`` lands in the right bucket
# without another edit here. ``created`` is deliberately NOT "running": a
# created-but-not-invoked run could sit forever and would be misleading in a
# "what is running right now" feed.
RUNNING_STATUSES = frozenset({"running", "in_progress", "queued", "started"})
ATTENTION_STATUSES = frozenset({"failed", "error", "blocked"})
RECENT_STATUSES = frozenset({"completed", "imported"})

# Bounds so a long-lived local DB doesn't return an unbounded feed. Pending
# captures are usually few, but cap them too so the popover stays compact.
_MAX_ATTENTION_RUNS = 10
_MAX_RECENT_RUNS = 6
_MAX_PENDING_CAPTURES = 20

_DETAIL_MAX_LEN = 140


def _short_detail(message: Optional[str]) -> Optional[str]:
    """First line of an error message, trimmed for a one-line popover row."""
    if not message:
        return None
    first_line = message.strip().splitlines()[0].strip() if message.strip() else ""
    if not first_line:
        return None
    if len(first_line) > _DETAIL_MAX_LEN:
        return first_line[: _DETAIL_MAX_LEN - 1].rstrip() + "…"
    return first_line


def _run_subtitle(job: Optional[Job]) -> Optional[str]:
    if job is None:
        return None
    return f"{job.title} — {job.company}"


@router.get("", response_model=ActivityRead)
def get_activity(db: Session = Depends(get_db)) -> ActivityRead:
    """Unified activity feed backing the sidebar activity center.

    Aggregates tailoring-run lifecycle state and pending browser-extension
    captures into a single, domain-agnostic feed so the bottom-left
    component never has to know about individual domain models. Grouped
    into ``running`` (active runs), ``attention`` (failed runs + pending
    captures), and ``recent`` (lately completed/imported runs).
    """
    runs = list(db.query(ClaudeRun).order_by(ClaudeRun.created_at.desc()).all())

    job_ids = {run.job_id for run in runs}
    jobs: dict[str, Job] = {}
    if job_ids:
        for job in db.query(Job).filter(Job.id.in_(job_ids)).all():
            jobs[job.id] = job

    running_items: list[ActivityItemRead] = []
    attention_items: list[ActivityItemRead] = []
    recent_items: list[ActivityItemRead] = []

    failed_seen = 0
    recent_seen = 0
    for run in runs:
        status = (run.status or "").lower()
        subtitle = _run_subtitle(jobs.get(run.job_id))
        started = run.started_at or run.created_at
        href = f"/runs/{run.id}"

        if status in RUNNING_STATUSES:
            running_items.append(
                ActivityItemRead(
                    id=run.id,
                    type="tailoring_run",
                    status="running",
                    group="running",
                    title="Tailoring resume",
                    subtitle=subtitle,
                    started_at=started,
                    href=href,
                )
            )
        elif status in ATTENTION_STATUSES:
            if failed_seen >= _MAX_ATTENTION_RUNS:
                continue
            failed_seen += 1
            attention_items.append(
                ActivityItemRead(
                    id=run.id,
                    type="tailoring_run",
                    status="failed",
                    group="attention",
                    title="Tailoring failed",
                    subtitle=subtitle,
                    detail=_short_detail(run.error_message)
                    or "Run did not complete",
                    started_at=started,
                    href=href,
                )
            )
        elif status in RECENT_STATUSES:
            if recent_seen >= _MAX_RECENT_RUNS:
                continue
            recent_seen += 1
            recent_items.append(
                ActivityItemRead(
                    id=run.id,
                    type="tailoring_run",
                    status=status,
                    group="recent",
                    title="Tailoring complete",
                    subtitle=subtitle,
                    started_at=run.completed_at or started,
                    href=href,
                )
            )

    pending = list(
        db.query(JobCapture)
        .filter(JobCapture.user_confirmed.is_(False))
        .order_by(JobCapture.created_at.desc())
        .all()
    )
    pending_count = len(pending)
    for capture in pending[:_MAX_PENDING_CAPTURES]:
        parts = [p for p in (capture.title, capture.company) if p]
        subtitle = " — ".join(parts) if parts else None
        attention_items.append(
            ActivityItemRead(
                id=capture.id,
                type="pending_capture",
                status="attention",
                group="attention",
                title="Capture needs review",
                subtitle=subtitle,
                detail=f"Captured from {capture.source_platform}"
                if capture.source_platform
                else None,
                started_at=capture.captured_at or capture.created_at,
                href=f"/captures/{capture.id}",
            )
        )

    summary = ActivitySummaryRead(
        running_count=len(running_items),
        attention_count=len(attention_items),
        pending_capture_count=pending_count,
    )
    items = running_items + attention_items + recent_items
    return ActivityRead(summary=summary, items=items)
