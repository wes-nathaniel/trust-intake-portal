"""Background-job coordinator for the page-by-page trust explainer.

Auto-fires on every trust_draft upload so admins never see a spinner and never
have to click a button. Progress is mirrored onto `case.trust_page_job` so the
UI can show a status even after a pod restart. Startup sweep marks orphaned
jobs as failed."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

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


async def _persist(db, case_id: str, job: Dict,
                   update_case_fn: Callable[[str, dict], Awaitable[None]]) -> None:
    try:
        await update_case_fn(case_id, {"trust_page_job": job})
    except Exception as e:
        logger.warning(f"trust_page_job persist failed for {case_id}: {e}")


async def start_page_explain_job(
    *,
    case_id: str,
    pdf_bytes: bytes,
    case_context: dict,
    admin_id: str,
    db,
    update_case_fn: Callable[[str, dict], Awaitable[None]],
) -> Dict:
    """Kick off the page-explain background task. If a job is already running
    for this case, returns the existing task_id (no duplicate work)."""
    existing = _jobs.get(case_id)
    if existing and existing.get("status") == "pending":
        return {"task_id": existing["task_id"], "status": "pending",
                "already_running": True}

    task_id = uuid.uuid4().hex[:12]
    job = {
        "task_id": task_id,
        "status": "pending",
        "started_at": _now_iso(),
        "last_progress_at": _now_iso(),
        "pages_done": 0,
        "pages_total": 0,
        "batches_done": 0,
        "batches_total": 0,
        "error": None,
        "finished_at": None,
        "admin_id": admin_id,
    }
    _jobs[case_id] = job
    await _persist(db, case_id, job, update_case_fn)

    async def _runner():
        import trust_page_explainer
        lock = _get_lock(case_id)
        async with lock:
            try:
                # 1. Extract page texts on a worker thread (avoids blocking loop)
                pages = await asyncio.to_thread(
                    trust_page_explainer.extract_page_texts, pdf_bytes
                )
                if not pages:
                    job["status"] = "failed"
                    job["error"] = (
                        "Could not extract text from the PDF (may be a scanned "
                        "image with no text layer)."
                    )
                    job["finished_at"] = _now_iso()
                    await _persist(db, case_id, job, update_case_fn)
                    return

                job["pages_total"] = len(pages)
                job["last_progress_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)

                # 2. Progress callback — persist after each batch completes
                async def progress_cb(done: int, total: int, count: int):
                    job["batches_done"] = done
                    job["batches_total"] = total
                    job["pages_done"] = count
                    job["last_progress_at"] = _now_iso()
                    await _persist(db, case_id, job, update_case_fn)
                    # Also mirror partial results onto the case as they arrive so
                    # the client viewer can render pages incrementally.

                # 3. Run the actual LLM explanations
                explanations = await trust_page_explainer.explain_pages(
                    pages, case_context or {}, progress_cb=progress_cb
                )

                # 4. Persist final results
                await update_case_fn(case_id, {
                    "trust_page_explanations": explanations,
                    "trust_page_explanations_generated_at": _now_iso(),
                    "trust_page_explanations_source_path": None,  # set by caller if needed
                })

                job["status"] = "completed"
                job["pages_done"] = len(explanations)
                job["finished_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)
                logger.info(
                    f"trust_page_job {task_id} for case {case_id}: "
                    f"completed with {len(explanations)} page explanations"
                )
            except Exception as e:
                logger.exception(f"trust_page_job {task_id} for case {case_id}: crashed")
                job["status"] = "failed"
                job["error"] = str(e)[:400]
                job["finished_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)

    asyncio.create_task(_runner())
    return {"task_id": task_id, "status": "pending", "already_running": False}


async def get_status(case_id: str, db) -> Optional[Dict]:
    job = _jobs.get(case_id)
    if job:
        return dict(job)
    try:
        case = await db.trust_cases.find_one(
            {"id": case_id}, {"_id": 0, "trust_page_job": 1}
        )
    except Exception as e:
        logger.warning(f"trust_page_job get_status DB lookup failed for {case_id}: {e}")
        return None
    if not case:
        return None
    return case.get("trust_page_job")


async def sweep_stuck_jobs_on_startup(
    db, update_case_fn: Callable[[str, dict], Awaitable[None]]
) -> int:
    """Startup sweep — orphan any `pending` page-explain jobs left over from a
    prior worker (their runners no longer exist)."""
    try:
        cursor = db.trust_cases.find(
            {"trust_page_job.status": "pending", "trust_page_job.finished_at": None},
            {"_id": 0, "id": 1, "trust_page_job": 1},
        )
        docs = await cursor.to_list(500)
    except Exception as e:
        logger.warning(f"page-explain sweep query failed: {e}")
        return 0
    n = 0
    for d in docs:
        job = dict(d.get("trust_page_job") or {})
        if job.get("status") != "pending":
            continue
        job["status"] = "failed"
        job["error"] = "Server restarted while explanations were being generated. Re-upload the PDF or click 'Regenerate' to retry."
        job["finished_at"] = _now_iso()
        try:
            await update_case_fn(d["id"], {"trust_page_job": job})
            n += 1
        except Exception as e:
            logger.warning(f"page-explain sweep persist failed for {d['id']}: {e}")
    if n:
        logger.info(f"page_explanation_jobs sweep: marked {n} orphaned job(s) as failed")
    return n
