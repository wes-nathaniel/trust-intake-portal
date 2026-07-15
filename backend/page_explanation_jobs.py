"""Background-job coordinator for the page-by-page trust explainer.

Auto-fires on every trust_draft upload so admins never see a spinner and never
have to click a button. Progress is mirrored onto `case.trust_page_job` so the
UI can show a status even after a pod restart.

RESUMABILITY (2026-07-15 hardening after Cloudflare 524 on production):
- Partial explanations are persisted onto the case (`trust_page_explanations`)
  after EVERY batch completes, not only at the end. If the pod cycles mid-run,
  the next boot can pick up from `batches_done` without losing the work
  already paid for.
- On startup, `sweep_stuck_jobs_on_startup(db, update_case_fn, resume_fn)`
  attempts to RESUME any pending job by re-reading the source PDF from object
  storage and re-firing `start_page_explain_job` with the batches_done offset.
  Only if the resume cannot be performed (missing PDF / no partials) does it
  fall back to marking the job failed."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable, List

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
    resume_from_batch: int = 0,
    prior_explanations: Optional[List[Dict]] = None,
) -> Dict:
    """Kick off the page-explain background task. If a job is already running
    for this case, returns the existing task_id (no duplicate work).

    Resumability: pass `resume_from_batch` (int) and `prior_explanations`
    (list of already-completed {page, text} rows) to continue where a prior
    process left off. The runner will skip the first N batches and merge new
    results with the prior ones before persisting."""
    existing = _jobs.get(case_id)
    if existing and existing.get("status") == "pending":
        return {"task_id": existing["task_id"], "status": "pending",
                "already_running": True}

    task_id = uuid.uuid4().hex[:12]
    prior = list(prior_explanations or [])
    job = {
        "task_id": task_id,
        "status": "pending",
        "started_at": _now_iso(),
        "last_progress_at": _now_iso(),
        "pages_done": len(prior),
        "pages_total": 0,
        "batches_done": max(0, int(resume_from_batch or 0)),
        "batches_total": 0,
        "error": None,
        "finished_at": None,
        "admin_id": admin_id,
        "resumed": bool(resume_from_batch),
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

                # Live-merge state — starts with any prior partials so we
                # never lose completed work across pod cycles.
                aggregated: List[Dict] = list(prior)

                # 2. Progress callback — persist after each batch completes,
                # AND mirror partial page explanations onto the case so the
                # client viewer can render pages as they come in AND a pod
                # cycle mid-run doesn't wipe the work.
                async def progress_cb(done_batches: int, total_batches: int,
                                      new_rows: List[Dict]):
                    if new_rows:
                        # Merge new rows into aggregated, dedupe by page
                        seen = {r.get("page") for r in aggregated}
                        for r in new_rows:
                            if r.get("page") not in seen:
                                aggregated.append(r)
                                seen.add(r.get("page"))
                    # Sort ascending by page for stable client rendering
                    aggregated.sort(key=lambda r: r.get("page") or 0)
                    job["batches_done"] = done_batches
                    job["batches_total"] = total_batches
                    job["pages_done"] = len(aggregated)
                    job["last_progress_at"] = _now_iso()
                    # Persist BOTH the job state and the incremental
                    # explanations so a mid-run pod cycle can resume without
                    # losing anything. This is the resumability contract.
                    try:
                        await update_case_fn(case_id, {
                            "trust_page_job": job,
                            "trust_page_explanations": aggregated,
                            "trust_page_explanations_updated_at": _now_iso(),
                        })
                    except Exception as e:
                        logger.warning(
                            f"trust_page_job partial persist failed for {case_id}: {e}"
                        )

                # 3. Run the actual LLM explanations (with resume offset)
                explanations = await trust_page_explainer.explain_pages(
                    pages, case_context or {},
                    progress_cb=progress_cb,
                    start_batch=int(resume_from_batch or 0),
                    prior=aggregated,
                )

                # 4. Persist final results (aggregated is already merged)
                final = explanations or aggregated
                await update_case_fn(case_id, {
                    "trust_page_explanations": final,
                    "trust_page_explanations_generated_at": _now_iso(),
                })

                job["status"] = "completed"
                job["pages_done"] = len(final)
                job["finished_at"] = _now_iso()
                await _persist(db, case_id, job, update_case_fn)
                logger.info(
                    f"trust_page_job {task_id} for case {case_id}: "
                    f"completed with {len(final)} page explanations "
                    f"(resumed_from_batch={resume_from_batch})"
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
    db,
    update_case_fn: Callable[[str, dict], Awaitable[None]],
    resume_fn: Optional[Callable[[str, int, List[Dict]], Awaitable[bool]]] = None,
) -> Dict[str, int]:
    """Startup sweep. Tries to RESUME any `pending` page-explain job by asking
    the caller (server.py) to re-load the PDF and re-fire the job with the
    batches_done offset. Falls back to marking failed if resume is impossible.

    `resume_fn(case_id, resume_from_batch, prior_explanations) -> bool`
        Returns True if the resume was successfully scheduled, False otherwise.

    Returns {resumed: n, failed: n} counts."""
    try:
        cursor = db.trust_cases.find(
            {"trust_page_job.status": "pending", "trust_page_job.finished_at": None},
            {"_id": 0, "id": 1, "trust_page_job": 1,
             "trust_page_explanations": 1, "trust_draft": 1},
        )
        docs = await cursor.to_list(500)
    except Exception as e:
        logger.warning(f"page-explain sweep query failed: {e}")
        return {"resumed": 0, "failed": 0}

    resumed = 0
    failed = 0
    for d in docs:
        job = dict(d.get("trust_page_job") or {})
        if job.get("status") != "pending":
            continue
        case_id = d.get("id")
        batches_done = int(job.get("batches_done") or 0)
        priors = list(d.get("trust_page_explanations") or [])
        has_pdf = bool((d.get("trust_draft") or {}).get("storage_path"))
        resumed_ok = False
        if resume_fn and has_pdf:
            try:
                resumed_ok = await resume_fn(case_id, batches_done, priors)
            except Exception as e:
                logger.warning(f"page-explain resume_fn failed for {case_id}: {e}")
                resumed_ok = False
        if resumed_ok:
            resumed += 1
            logger.info(
                f"page-explain sweep: RESUMED case {case_id} from batch "
                f"{batches_done} ({len(priors)} pages already saved)"
            )
            continue
        # Could not resume — mark failed so the UI can prompt for regenerate
        job["status"] = "failed"
        job["error"] = (
            "Server restarted mid-run and the source PDF could not be reloaded. "
            "Click 'Regenerate' to retry."
        )
        job["finished_at"] = _now_iso()
        try:
            await update_case_fn(case_id, {"trust_page_job": job})
            failed += 1
        except Exception as e:
            logger.warning(f"page-explain sweep persist failed for {case_id}: {e}")
    if resumed or failed:
        logger.info(
            f"page_explanation_jobs sweep: resumed={resumed} failed={failed}"
        )
    return {"resumed": resumed, "failed": failed}
