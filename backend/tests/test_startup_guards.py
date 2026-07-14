"""
Startup guard tests for FastAPI lifespan (server.py ~L4810).
Verifies startup completes even when:
  1. A conflicting TTL index exists (IndexOptionsConflict).
  2. Admin's password_hash is malformed (bcrypt ValueError).
  3. Admin's password_hash field is missing (KeyError path).
  4. Admin doc is missing entirely (fresh seed path).
After each test, state is restored via the handler's own refresh path.
"""
import os
import time
import subprocess
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trust-intake-portal.preview.emergentagent.com").rstrip("/")
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "trust_portal"
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"
BACKEND_LOG = "/var/log/supervisor/backend.err.log"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def restart_backend_and_wait(timeout: int = 30) -> float:
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
    deadline = time.time() + timeout
    up = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/", timeout=3)
            if r.status_code == 200:
                up = True
                break
        except Exception:
            pass
        time.sleep(0.5)
    assert up, "Backend did not come up within timeout"
    time.sleep(1.0)
    t0 = time.time()
    lr = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    latency = time.time() - t0
    assert lr.status_code == 200, f"Login failed after restart: {lr.status_code} {lr.text}"
    return latency


def log_since_last_startup() -> str:
    try:
        with open(BACKEND_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 40000))
            data = f.read().decode("utf-8", errors="ignore")
    except FileNotFoundError:
        return ""
    idx = data.rfind("Lifespan startup begin")
    return data[idx:] if idx != -1 else data


# ---------- STARTUP GUARD 1: IndexOptionsConflict ----------
def test_guard1_index_options_conflict_does_not_crash(db):
    # Setup: create conflicting TTL index
    try:
        db.invites.drop_index("expires_at_1")
    except Exception:
        pass
    db.invites.create_index("expires_at", expireAfterSeconds=999)

    try:
        latency = restart_backend_and_wait()
        log = log_since_last_startup()
        assert "Lifespan startup begin" in log, "Missing startup-begin log line"
        assert "Lifespan startup complete" in log, f"Startup did not complete (crash!):\n{log[-2000:]}"
        assert ("Index create skipped on invites" in log) or ("IndexOptionsConflict" in log), \
            "Expected index-conflict warning missing"
        assert latency < 3.0, f"Login too slow: {latency:.2f}s"
        st = subprocess.run(["sudo", "supervisorctl", "status", "backend"], capture_output=True, text=True)
        assert "RUNNING" in st.stdout
    finally:
        try:
            db.invites.drop_index("expires_at_1")
        except Exception:
            pass
        db.invites.create_index("expires_at", expireAfterSeconds=0)
        restart_backend_and_wait()  # boot back to clean state


# ---------- STARTUP GUARD 2a: Malformed password_hash ----------
def test_guard2a_malformed_password_hash_refreshes(db):
    db.users.update_one({"email": ADMIN_EMAIL},
                        {"$set": {"password_hash": "not-a-real-bcrypt-hash"}})
    restart_backend_and_wait()
    log = log_since_last_startup()
    assert "Lifespan startup complete" in log
    # Admin login still works because handler refreshed the hash
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"Admin login broken: {r.text}"
    # Verify hash was refreshed to a valid bcrypt
    doc = db.users.find_one({"email": ADMIN_EMAIL})
    assert doc.get("password_hash", "").startswith("$2"), "Hash was not refreshed to bcrypt format"


# ---------- STARTUP GUARD 2b: Missing password_hash field ----------
def test_guard2b_missing_password_hash_field_refreshes(db):
    db.users.update_one({"email": ADMIN_EMAIL}, {"$unset": {"password_hash": ""}})
    restart_backend_and_wait()
    log = log_since_last_startup()
    assert "Lifespan startup complete" in log
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"Admin login broken: {r.text}"
    doc = db.users.find_one({"email": ADMIN_EMAIL})
    assert doc.get("password_hash", "").startswith("$2")


# ---------- STARTUP GUARD 3: Missing admin doc entirely ----------
def test_guard3_missing_admin_doc_is_reseeded(db):
    db.users.delete_one({"email": ADMIN_EMAIL})
    restart_backend_and_wait()
    log = log_since_last_startup()
    assert "Lifespan startup complete" in log
    doc = db.users.find_one({"email": ADMIN_EMAIL})
    assert doc is not None, "Admin doc not re-seeded"
    assert doc.get("role") == "admin"
    assert doc.get("password_hash", "").startswith("$2")
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200


# ---------- REGRESSION: Clean startup ----------
def test_regression_clean_startup_no_warnings():
    # Force a fresh restart with known-clean state
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
    time.sleep(3.0)
    # Poll until up
    for _ in range(30):
        try:
            if requests.get(f"{BASE_URL}/api/", timeout=3).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    log = log_since_last_startup()
    assert "Lifespan startup begin" in log
    assert "Lifespan startup complete" in log
    assert "Index create skipped" not in log, f"Unexpected index warning on clean boot:\n{log}"
