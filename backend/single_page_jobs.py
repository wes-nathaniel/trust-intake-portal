"""Per-page trust-explanation regeneration.

The main `page_explanation_jobs` module does batched regeneration of ALL
pages. Admins occasionally need to redo just one page (e.g., they fixed a
typo in the intake and want that single page's explanation re-generated
using the corrected data). This module owns that single-page path so:

  - Clicking Regenerate on page 17 regenerates only page 17.
  - The full-batch job status on the case is untouched — the client-side
    progress bar for the full run does not flip back to 'pending'.
  - Retries happen inside the runner (2 attempts) so a transient LLM
    hiccup doesn't leave the page blank and force the admin to click
    Regenerate repeatedly.

Result merging is careful: the existing `trust_page_explanations` list is
read, the target page is replaced (or appended), then the whole list is
persisted. No other pages are touched.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable, Dict, Optional

logger = logging.getLogger(__name__)

# In-memory job registry, keyed by f"{case_id}:{page_num}". Status is also
# mirrored to Mongo (`trust_page_single_jobs` map on the case) so clients
# can poll status across a pod restart.
_jobs: Dict[str, Dict] = {}
_locks: Dict[str, asyncio.Lock] = {}

# Retry budget for single-page LLM calls. Each attempt gets the full
# LLM_CALL_TIMEOUT_SEC from trust_page_explainer (85s). Two attempts fit
# comfortably under the Cloudflare 524 window because the ADMIN endpoint
# returns immediately — the retries happen in the background task.
MAX_ATTEMPTS = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(case_id: str, page_num: int) -> str:
    return f"{case_id}:{page_num}"


def _lock(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def start_single_page_regenerate(
    *,
    case_id: str,
    page_num: int,
    pdf_bytes: bytes,
    case_context: dict,
    admin_id: str,
    db,
    update_case_fn: Callable[[str, dict], Awaitable[None]],
) -> Dict:
    """Kick off a background task that regenerates the explanation for one
    specific page. Idempotent — a duplicate request while a job is pending
    returns the existing task_id."""
    key = _key(case_id, page_num)
    existing = _jobs.get(key)
    if existing and existing.get("status") == "pending":
        return {"task_id": existing["task_id"], "status": "pending",
                "already_running": True, "page": page_num}

    task_id = uuid.uuid4().hex[:12]
    job = {
        "task_id": task_id,
        "page": page_num,
        "status": "pending",
        "attempt": 0,
        "started_at": _now_iso(),
        "finished_at": None,
        "admin_id": admin_id,
        "error": None,
    }
    _jobs[key] = job

    async def _runner():
        import trust_page_explainer
        lock = _lock(key)
        async with lock:
            try:
                # 1. Extract page text from the PDF (worker thread; PyMuPDF blocks)
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
                    return
                if page_num < 1 or page_num > len(pages):
                    job["status"] = "failed"
                    job["error"] = f"Page {page_num} is out of range (PDF has {len(pages)} pages)."
                    job["finished_at"] = _now_iso()
                    return

                # 2. Retry the LLM call up to MAX_ATTEMPTS times. This is the
                #    heart of the "times out and comes back blank" fix: the
                #    LLM occasionally returns unparseable JSON on tiny single-
                #    page prompts, and _run_batch silently returns []. We
                #    catch that and try again before giving up.
                text = ""
                last_error = None
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    job["attempt"] = attempt
                    try:
                        text = await trust_page_explainer.explain_single_page(
                            pages[page_num - 1], page_num, case_context
                        )
                    except Exception as e:
                        last_error = str(e)[:200]
                        logger.warning(
                            f"single-page regen attempt {attempt} for "
                            f"{case_id} p{page_num} raised: {e}"
                        )
                        text = ""
                    if text and text.strip():
                        break
                    last_error = last_error or "LLM returned an empty response"
                    logger.info(
                        f"single-page regen attempt {attempt}/{MAX_ATTEMPTS} "
                        f"for {case_id} p{page_num} produced no text; retrying"
                    )

                if not text or not text.strip():
                    job["status"] = "failed"
                    job["error"] = (
                        f"AI produced no text for page {page_num} after "
                        f"{MAX_ATTEMPTS} attempts. {last_error}. Please try again."
                    )
                    job["finished_at"] = _now_iso()
                    return

                # 3. Merge into existing explanations — REPLACE the target
                #    page, leave every other page untouched.
                doc = await db.trust_cases.find_one(
                    {"id": case_id},
                    {"_id": 0, "trust_page_explanations": 1},
                )
                existing_exps = (doc or {}).get("trust_page_explanations") or []
                merged = [e for e in existing_exps if e.get("page") != page_num]
                merged.append({"page": page_num, "text": text})
                merged.sort(key=lambda r: r.get("page") or 0)

                await update_case_fn(case_id, {
                    "trust_page_explanations": merged,
                    "trust_page_explanations_updated_at": _now_iso(),
                    f"trust_page_single_jobs.{page_num}": job,
                })

                job["status"] = "completed"
                job["finished_at"] = _now_iso()
                logger.info(
                    f"single-page regen {task_id} for case {case_id} p{page_num}: "
                    f"completed on attempt {job['attempt']} ({len(text)} chars)"
                )
            except Exception as e:
                logger.exception(
                    f"single-page regen {task_id} for {case_id} p{page_num}: crashed"
                )
                job["status"] = "failed"
                job["error"] = str(e)[:400]
                job["finished_at"] = _now_iso()

    asyncio.create_task(_runner())
    return {"task_id": task_id, "status": "pending",
            "already_running": False, "page": page_num}


def get_status(case_id: str, page_num: int) -> Optional[Dict]:
    return _jobs.get(_key(case_id, page_num))
