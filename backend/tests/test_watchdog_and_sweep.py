"""Watchdog + startup-sweep tests for trust auto-extract.

Covers the 4 backend fixes from iteration 13:
  1. trust_extractor._extract_pdf_text now runs via asyncio.to_thread (verified by grep)
  2. GET extract-status endpoint wrapped in try/except → returns JSON on any error
  3. Watchdog: pending job > 300s w/o progress -> flipped to failed with 'stalled' error
  4. Startup sweep: orphaned pending jobs marked failed on backend restart
"""
import asyncio
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "trust_portal"


# ---------- FIXTURES ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def client_session():
    s = requests.Session()
    email = f"testclient_wd_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "WD Test"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


async def _seed_job(db, case_id: str, job: dict):
    await db.trust_cases.update_one({"id": case_id}, {"$set": {"trust_extract_job": job}})


async def _get_case(db, case_id: str):
    return await db.trust_cases.find_one({"id": case_id}, {"_id": 0})


def _make_case(client_session):
    r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
    assert r.status_code == 200
    return r.json()["id"]


# ---------- STATIC / CODE-REVIEW CHECKS ----------
class TestCodeReview:
    def test_pdf_extract_uses_to_thread(self):
        """Fix 1: _extract_pdf_text must be offloaded via asyncio.to_thread."""
        src = Path("/app/backend/trust_extractor.py").read_text()
        assert "asyncio.to_thread(_extract_pdf_text" in src, \
            "pypdfium2 call not wrapped in asyncio.to_thread — event loop can still block"

    def test_extract_status_has_try_except(self):
        """Fix 2: admin_auto_extract_status wrapped in try/except returning error envelope."""
        src = Path("/app/backend/server.py").read_text()
        assert "async def admin_auto_extract_status" in src
        # ensure error return envelope exists
        assert '"status": "error"' in src or "'status': 'error'" in src

    def test_startup_calls_sweep(self):
        src = Path("/app/backend/server.py").read_text()
        assert "extract_jobs.sweep_stuck_jobs_on_startup" in src


# ---------- WATCHDOG ----------
class TestWatchdog:

    @pytest.mark.asyncio
    async def test_stuck_pending_flipped_to_failed(self, admin_session, client_session, db):
        cid = _make_case(client_session)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        stuck_job = {
            "task_id": "stucktest01",
            "status": "pending",
            "started_at": stale,
            "sections_count": 0,
            "batches_done": 0,
            "batches_total": 0,
            "error": None,
            "finished_at": None,
            "admin_id": "admin-test",
        }
        await _seed_job(db, cid, stuck_job)

        # Also clear the in-memory _jobs dict (imported by server) so it falls
        # back to the persisted copy. We can't easily reach it from here, but
        # since this task_id was never started in-process, _jobs won't have it.

        r = admin_session.get(f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "failed", f"Expected failed, got {data}"
        assert data.get("error") and "stalled" in data["error"].lower(), \
            f"Expected 'stalled' in error, got {data.get('error')}"

        # Verify persisted to DB
        case = await _get_case(db, cid)
        job = case.get("trust_extract_job") or {}
        assert job.get("status") == "failed"
        assert job.get("finished_at") is not None
        assert "stalled" in (job.get("error") or "").lower()

    @pytest.mark.asyncio
    async def test_fresh_pending_not_flipped(self, admin_session, client_session, db):
        cid = _make_case(client_session)
        fresh = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        fresh_job = {
            "task_id": "freshtest01",
            "status": "pending",
            "started_at": fresh,
            "sections_count": 0,
            "batches_done": 0,
            "batches_total": 0,
            "error": None,
            "finished_at": None,
            "admin_id": "admin-test",
        }
        await _seed_job(db, cid, fresh_job)

        r = admin_session.get(f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending", f"Fresh job should still be pending, got {data}"

        case = await _get_case(db, cid)
        assert (case.get("trust_extract_job") or {}).get("status") == "pending"


# ---------- STARTUP SWEEP ----------
class TestStartupSweep:

    @pytest.mark.asyncio
    async def test_sweep_marks_orphaned_pending_failed(self, admin_session, client_session, db):
        cid = _make_case(client_session)
        orphan = {
            "task_id": "orphan01ab",
            "status": "pending",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "sections_count": 0,
            "batches_done": 0,
            "batches_total": 0,
            "error": None,
            "finished_at": None,
            "admin_id": "admin-test",
        }
        await _seed_job(db, cid, orphan)

        # Restart backend
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)

        # Wait for backend to come back and startup handler to finish
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            try:
                h = requests.get(f"{API}/health", timeout=3)
                if h.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(2)
        # If /api/health missing, just probe login page
        if not ready:
            for _ in range(10):
                try:
                    requests.get(f"{BASE_URL}/", timeout=3)
                    ready = True
                    break
                except Exception:
                    time.sleep(2)
        # Small extra grace for startup sweep to persist
        time.sleep(3)

        case = await _get_case(db, cid)
        job = case.get("trust_extract_job") or {}
        assert job.get("status") == "failed", f"Sweep did not flip orphan: {job}"
        assert "Server restarted" in (job.get("error") or ""), \
            f"Expected 'Server restarted' error, got {job.get('error')}"
        assert job.get("finished_at") is not None

    @pytest.mark.asyncio
    async def test_sweep_leaves_completed_alone(self, client_session, db):
        cid = _make_case(client_session)
        completed = {
            "task_id": "done01ab",
            "status": "completed",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "sections_count": 4,
            "batches_done": 2,
            "batches_total": 2,
            "error": None,
            "admin_id": "admin-test",
        }
        await _seed_job(db, cid, completed)

        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
        # give startup a moment
        time.sleep(6)

        case = await _get_case(db, cid)
        job = case.get("trust_extract_job") or {}
        assert job.get("status") == "completed", f"Completed job was disturbed: {job}"


# ---------- LOG VERIFICATION ----------
class TestSweepLog:
    def test_backend_log_contains_sweep_line(self):
        """After the restarts above, backend log should have at least one
        `sweep_stuck_jobs_on_startup: marked N orphaned job(s) as failed` line."""
        logs = ""
        for p in ("/var/log/supervisor/backend.err.log",
                  "/var/log/supervisor/backend.out.log"):
            try:
                logs += Path(p).read_text()[-100_000:]
            except Exception:
                continue
        assert "sweep_stuck_jobs_on_startup" in logs, \
            "sweep log line missing from backend logs"
