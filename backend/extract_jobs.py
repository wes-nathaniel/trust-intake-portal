"""Background job manager for the trust-section auto-extract flow.

The API endpoint returns 202 immediately with a task id, and the actual
Claude extraction runs as an asyncio background task. Job state is kept:

  1. In-memory (`_jobs` dict) — fastest lookups for the polling endpoint.
  2. Mirrored onto the case doc under `trust_extract_job` so a backend
     restart mid-job doesn't leave the UI polling forever.

Public API:
  start_extract_job(case_id, pdf_bytes, filename, admin_id, db, update_case_fn)
      -> {task_id, status: "pending"}
  get_status(case_id, db) -> {task_id, status, sections_count, ...}
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

# case_id -> job info dict
_jobs: Dict[str, Dict] = {}
_locks: Dict[str, asyncio.Lock] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_lock(case_id: str) -> asyncio.Lock:
    lock = _locks.get(case_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[case_id] = lock
    return lock


async def _persist(db, case_id: str, job: Dict, update_case_fn: Callable[[str, dict], Awaitable[None]]):
    """Mirror the in-memory job onto the case doc (so a restart doesn't lose it)."""
    try:
        await update_case_fn(case_id, {"trust_extract_job": job})
    except Exception as e:
        logger.warning(f"trust_extract_job persist failed for {case_id}: {e}")


async def start_extract_job(
    *,
    case_id: str,
    pdf_bytes: bytes,
    filename: str,
    admin_id: str,
    db,
    update_case_fn: Callable[[str, dict], Awaitable[None]],
    on_complete_updates: Optional[Callable[[list], Awaitable[dict]]] = None,
) -> Dict:
    """Kick off a background extraction. Returns {task_id, status='pending'}.

    If a job is already running for this case, returns the existing task_id
    (no duplicate work)."""
    existing = _jobs.get(case_id)
    if existing and existing.get("status") == "pending":
        return {"task_id": existing["task_id"], "status": "pending",
                "already_running": True}

    task_id = uuid.uuid4().hex[:12]
    job = {
        "task_id": task_id,
        "status": "pending",
        "started_at": _now_iso(),
        "sections_count": 0,
        "batches_done": 0,
        "batches_total": 0,
        "error": None,
        "finished_at": None,
        "admin_id": admin_id,
    }
    _jobs[case_id] = job
    await _persist(db, case_id, job, update_case_fn)

    async def _runner():
        # Import here to avoid a circular import (server.py imports us).
        import trust_extractor
        lock = _get_lock(case_id)
        async with lock:
            try:
                async def progress_cb(done: int, total: int, count: int):
                    job["batches_done"] = done
                    job["batches_total"] = total
                    job["sections_count"] = count
                    await _persist(db, case_id, job, update_case_fn)

                sections = await trust_extractor.extract_trust_sections(
                    pdf_bytes, filename, progress_cb=progress_cb
                )

                if not sections:
                    job["status"] = "failed"
                    job["error"] = (
                        "No articles detected — the PDF may be a scanned image "
                        "(no text layer) or an unsupported format."
                    )
                    job["finished_at"] = _now_iso()
                    await _persist(db, case_id, job, update_case_fn)
                    return

                # Persist the sections onto the case (draft slot)
                updates = {
                    "trust_sections_draft": sections,
                    "trust_sections_draft_created_at": _now_iso(),
                    "trust_sections_draft_created_by": admin_id,
                }
                if on_complete_updates:
                    try:
                        extra = await on_complete_updates(sections)
                        if isinstance(extra, dict):
                            updates.update(extra)
                    except Exception as e:
                        logger.warning(f"on_complete_updates hook failed: {e}")
                await update_case_fn(case_id, updates)

                job["status"] = "completed"
                job["sections_count"] = len(sections)
                job["finished_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)
                logger.info(
                    f"trust_extract_job {task_id} for case {case_id}: "
                    f"completed with {len(sections)} sections"
                )
            except Exception as e:
                logger.exception(f"trust_extract_job {task_id} for case {case_id}: crashed")
                job["status"] = "failed"
                job["error"] = str(e)[:400]
                job["finished_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)

    asyncio.create_task(_runner())
    return {"task_id": task_id, "status": "pending", "already_running": False}


async def get_status(case_id: str, db) -> Optional[Dict]:
    """Look up the current job status. Prefers in-memory (freshest), falls
    back to the persisted copy on the case doc so restarts don't lose state."""
    job = _jobs.get(case_id)
    if job:
        return dict(job)
    # Fallback: read from the case doc
    try:
        case = await db.trust_cases.find_one(
            {"id": case_id},
            {"_id": 0, "trust_extract_job": 1, "trust_sections_draft": 1},
        )
    except Exception as e:
        logger.warning(f"get_status: DB lookup failed for {case_id}: {e}")
        return None
    if not case:
        return None
    return case.get("trust_extract_job")
