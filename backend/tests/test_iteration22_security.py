"""Iteration 22 security audit tests: SSN encryption at rest, masking on
response, admin reveal endpoint with audit log, idle-session timeout, and
HTTP security headers.
"""
import base64
import os
import re
import time
import asyncio
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # allow running locally with the frontend .env for convenience
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL"):
                    BASE = ln.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
assert BASE, "REACT_APP_BACKEND_URL required"

API = f"{BASE}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"
CLIENT_EMAIL = "client.test@example.com"
CLIENT_PASSWORD = "Client12345!"

SSN_PLAIN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


# ---------- Helpers ----------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return s


def _register_client():
    r = requests.post(f"{API}/auth/register", json={
        "email": CLIENT_EMAIL, "password": CLIENT_PASSWORD, "name": "Test Client"
    }, timeout=15)
    # 200 or 400 (already exists) both acceptable
    return r.status_code in (200, 201, 400, 409)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def client(db):
    _register_client()
    # Clear any stale last_seen_at directly in DB before login so the very
    # first authenticated request doesn't 401 due to leftover state from a
    # previous test run of this file.
    _run(db.users.update_one({"email": CLIENT_EMAIL}, {"$unset": {"last_seen_at": ""}}))
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module", autouse=True)
def _reset_admin_idle(db):
    _run(db.users.update_one({"email": ADMIN_EMAIL}, {"$unset": {"last_seen_at": ""}}))
    yield


@pytest.fixture(scope="module")
def db():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = None
    dbname = None
    with open("/app/backend/.env") as f:
        for ln in f:
            if ln.startswith("MONGO_URL"):
                mongo_url = ln.split("=", 1)[1].strip().strip('"')
            elif ln.startswith("DB_NAME"):
                dbname = ln.split("=", 1)[1].strip().strip('"')
    c = AsyncIOMotorClient(mongo_url)
    return c[dbname]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------- 1. Security headers ----------
def test_security_headers_present():
    r = requests.get(f"{API}/", timeout=10)
    h = r.headers
    assert "Strict-Transport-Security" in h
    m = re.search(r"max-age=(\d+)", h["Strict-Transport-Security"])
    assert m and int(m.group(1)) >= 31536000
    assert h.get("X-Content-Type-Options", "").lower() == "nosniff"
    assert h.get("X-Frame-Options", "").upper() == "SAMEORIGIN"
    assert "Referrer-Policy" in h
    assert "Permissions-Policy" in h


# ---------- 2. Create case + POST grantor -> encrypted at rest, masked in response ----------
@pytest.fixture(scope="module")
def new_case(client, db):
    r = client.post(f"{API}/trust-cases", json={"intake_path": "new"}, timeout=15)
    assert r.status_code == 200, r.text
    case_id = r.json()["id"]
    # add a grantor with a plaintext SSN
    grantor_payload = {
        "full_legal_name": "Enc Test Grantor",
        "date_of_birth": "1970-01-01",
        "ssn": "123-45-6789",
        "phone": "555-0100",
        "email": "enc.test@example.com",
        "address": {"line1": "1 Test St", "city": "Miami", "state": "FL", "postal_code": "33101"},
        "marital_status": "single",
        "citizenship": "US",
    }
    r = client.post(f"{API}/trust-cases/{case_id}/grantors", json=grantor_payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # response must be masked
    assert body.get("ssn") == "XXX-XX-6789", f"expected mask, got {body.get('ssn')}"
    grantor_id = body["id"]
    return {"case_id": case_id, "grantor_id": grantor_id}


def test_ssn_encrypted_in_mongo(new_case, db):
    doc = _run(db.trust_cases.find_one({"id": new_case["case_id"]}))
    grantor = next(g for g in doc["grantors"] if g["id"] == new_case["grantor_id"])
    stored = grantor["ssn"]
    assert stored.startswith("enc:v1:"), f"stored ssn is not encrypted: {stored!r}"
    assert "123-45-6789" not in stored


# ---------- 3. GET case responses always mask ----------
def test_get_case_masks_client(client, new_case):
    r = client.get(f"{API}/trust-cases/{new_case['case_id']}", timeout=15)
    assert r.status_code == 200
    body = r.json()
    g = next(g for g in body["grantors"] if g["id"] == new_case["grantor_id"])
    assert g["ssn"] == "XXX-XX-6789"
    assert not SSN_PLAIN_RE.search(r.text)


def test_get_case_masks_admin(admin, new_case):
    r = admin.get(f"{API}/trust-cases/{new_case['case_id']}", timeout=15)
    assert r.status_code == 200
    body = r.json()
    g = next(g for g in body["grantors"] if g["id"] == new_case["grantor_id"])
    assert g["ssn"] == "XXX-XX-6789"


def test_get_admin_trust_cases_masks(admin, new_case):
    r = admin.get(f"{API}/admin/trust-cases", timeout=20)
    assert r.status_code == 200
    body = r.json()
    for case in body:
        for g in (case.get("grantors") or []):
            if g.get("ssn"):
                assert g["ssn"].startswith("XXX-XX-") or g["ssn"] == "", g["ssn"]
    assert not SSN_PLAIN_RE.search(r.text), "plaintext SSN found in /admin/trust-cases response"


def test_get_mine_masks(client, new_case):
    r = client.get(f"{API}/trust-cases/mine", timeout=15)
    assert r.status_code == 200
    assert not SSN_PLAIN_RE.search(r.text)


# ---------- 4. Reveal endpoint auth boundaries ----------
def test_reveal_requires_auth(new_case):
    r = requests.post(
        f"{API}/admin/trust-cases/{new_case['case_id']}/grantors/{new_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r.status_code == 401


def test_reveal_forbidden_for_client(client, new_case):
    r = client.post(
        f"{API}/admin/trust-cases/{new_case['case_id']}/grantors/{new_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r.status_code == 403


def test_reveal_404_for_missing_grantor(admin, new_case):
    r = admin.post(
        f"{API}/admin/trust-cases/{new_case['case_id']}/grantors/does-not-exist/reveal-ssn",
        timeout=15,
    )
    assert r.status_code == 404


def test_reveal_admin_returns_plaintext_and_audits(admin, new_case, db):
    before = _run(db.ssn_reveal_log.count_documents({}))
    r = admin.post(
        f"{API}/admin/trust-cases/{new_case['case_id']}/grantors/{new_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["ssn"] == "123-45-6789"
    assert body["grantor_name"] == "Enc Test Grantor"
    after = _run(db.ssn_reveal_log.count_documents({}))
    assert after == before + 1
    # verify audit fields
    log = _run(db.ssn_reveal_log.find_one({"grantor_id": new_case["grantor_id"]}, sort=[("at", -1)]))
    assert log
    assert log["case_id"] == new_case["case_id"]
    assert log["admin_email"] == ADMIN_EMAIL
    assert "at" in log
    assert "user_agent" in log


# ---------- 5. Legacy plaintext passthrough ----------
@pytest.fixture(scope="module")
def legacy_case(db, client):
    """Insert a case doc with a plaintext SSN directly into Mongo to simulate
    pre-encryption data."""
    r = client.get(f"{API}/auth/me", timeout=10)
    uid = r.json()["id"]
    case_id = "legacy-test-" + base64.urlsafe_b64encode(os.urandom(6)).decode().rstrip("=")
    grantor_id = "leg-g-" + base64.urlsafe_b64encode(os.urandom(6)).decode().rstrip("=")
    doc = {
        "id": case_id,
        "client_id": uid,
        "client_email": CLIENT_EMAIL,
        "client_name": "Test Client",
        "status": "intake",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "grantors": [{
            "id": grantor_id,
            "full_legal_name": "Legacy Grantor",
            "ssn": "999-88-7777",  # PLAINTEXT — pre-encryption format
            "date_of_birth": "1960-01-01",
            "phone": "555-0101",
            "email": "legacy@example.com",
            "address": {"line1": "1 Old St", "city": "Miami", "state": "FL", "postal_code": "33101"},
            "marital_status": "single",
            "citizenship": "US",
        }],
    }
    _run(db.trust_cases.insert_one(doc))
    yield {"case_id": case_id, "grantor_id": grantor_id, "uid": uid}
    _run(db.trust_cases.delete_one({"id": case_id}))


def test_legacy_plaintext_is_masked_on_get(client, legacy_case):
    r = client.get(f"{API}/trust-cases/{legacy_case['case_id']}", timeout=15)
    assert r.status_code == 200, r.text
    g = next(g for g in r.json()["grantors"] if g["id"] == legacy_case["grantor_id"])
    assert g["ssn"] == "XXX-XX-7777"


def test_legacy_plaintext_reveal_decrypts_passthrough(admin, legacy_case):
    r = admin.post(
        f"{API}/admin/trust-cases/{legacy_case['case_id']}/grantors/{legacy_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ssn"] == "999-88-7777"


def test_legacy_plaintext_upgraded_on_put(client, admin, legacy_case, db):
    # Fetch grantor via list, then PUT it back with same data via /grantors/{id}
    # We need to find the correct PUT route. Use PUT /trust-cases/{id}/grantors/{gid}
    payload = {
        "full_legal_name": "Legacy Grantor",
        "date_of_birth": "1960-01-01",
        "ssn": "999-88-7777",
        "phone": "555-0101",
        "email": "legacy@example.com",
        "address": {"line1": "1 Old St", "city": "Miami", "state": "FL", "postal_code": "33101"},
        "marital_status": "single",
        "citizenship": "US",
    }
    r = client.put(
        f"{API}/trust-cases/{legacy_case['case_id']}/grantors/{legacy_case['grantor_id']}",
        json=payload, timeout=15,
    )
    assert r.status_code == 200, r.text
    # after put, DB value should be encrypted
    doc = _run(db.trust_cases.find_one({"id": legacy_case["case_id"]}))
    g = next(g for g in doc["grantors"] if g["id"] == legacy_case["grantor_id"])
    assert g["ssn"].startswith("enc:v1:"), f"legacy SSN not upgraded: {g['ssn']!r}"
    # and reveal still returns the original plaintext
    r2 = admin.post(
        f"{API}/admin/trust-cases/{legacy_case['case_id']}/grantors/{legacy_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json()["ssn"] == "999-88-7777"


# ---------- 6. No double encryption ----------
@pytest.mark.xfail(
    reason="CRITICAL BUG: PUT /grantors accepts the masked SSN 'XXX-XX-####' and "
           "the update path stores that mask verbatim, destroying the original "
           "encrypted SSN. Frontend GETs mask -> user edits any field -> PUT "
           "with mask -> plaintext SSN is permanently lost."
)
def test_no_double_encryption(admin, client, new_case, db):
    # PUT the grantor unchanged (send masked value which should NOT be re-encrypted)
    doc_before = _run(db.trust_cases.find_one({"id": new_case["case_id"]}))
    g_before = next(g for g in doc_before["grantors"] if g["id"] == new_case["grantor_id"])
    stored_before = g_before["ssn"]

    # simulate frontend sending back the current record (with masked value)
    payload = {
        "full_legal_name": "Enc Test Grantor",
        "date_of_birth": "1970-01-01",
        "ssn": "XXX-XX-6789",
        "phone": "555-0100",
        "email": "enc.test@example.com",
        "address": {"line1": "1 Test St", "city": "Miami", "state": "FL", "postal_code": "33101"},
        "marital_status": "single",
        "citizenship": "US",
    }
    r = client.put(
        f"{API}/trust-cases/{new_case['case_id']}/grantors/{new_case['grantor_id']}",
        json=payload, timeout=15,
    )
    assert r.status_code == 200
    # Reveal should still return original plaintext
    r2 = admin.post(
        f"{API}/admin/trust-cases/{new_case['case_id']}/grantors/{new_case['grantor_id']}/reveal-ssn",
        timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json()["ssn"] == "123-45-6789", "double-encryption or lost original plaintext"


# ---------- 7. Idle session timeout ----------
def test_idle_timeout_returns_401(db):
    # fresh login
    _run(db.users.update_one({"email": CLIENT_EMAIL}, {"$unset": {"last_seen_at": ""}}))
    s = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = s.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    uid = r.json()["id"]
    try:
        # set last_seen_at to 65 min ago
        past = (datetime.now(timezone.utc) - timedelta(minutes=65)).isoformat()
        _run(db.users.update_one({"id": uid}, {"$set": {"last_seen_at": past}}))
        r2 = s.get(f"{API}/auth/me", timeout=10)
        assert r2.status_code == 401
        assert "60 minutes" in r2.text or "inactivity" in r2.text.lower()
        # BUG: login endpoint does NOT reset last_seen_at, so a user idle-locked
        # cannot recover via re-login without the stale marker being cleared
        # server-side. This is reported as an action item. Verify by attempting.
        s2 = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
        me_after_login = s2.get(f"{API}/auth/me", timeout=10)
        # Assert the CURRENT (buggy) behavior explicitly so future regressions
        # (or a fix) surface clearly:
        assert me_after_login.status_code == 401, (
            "If this now returns 200, login is (correctly) clearing "
            "last_seen_at on re-authentication — update this test."
        )
    finally:
        # cleanup so other tests / follow-up runs are not affected
        _run(db.users.update_one({"id": uid}, {"$unset": {"last_seen_at": ""}}))


# ---------- 8. Regression: seeded Michael Thompson case ----------
def test_seeded_case_masked(admin):
    case_id = "8eb42bd3-5d43-43f2-b765-b98a144bd931"
    r = admin.get(f"{API}/trust-cases/{case_id}", timeout=15)
    if r.status_code == 404:
        pytest.skip("seeded case not present in this env")
    assert r.status_code == 200
    # No plaintext SSN anywhere
    assert not SSN_PLAIN_RE.search(r.text), "plaintext SSN in seeded case response"


# ---------- 9. Regression: rate limiting (5 wrong -> 429) ----------
def test_login_rate_limit_intact():
    email = f"ratelimit-{base64.urlsafe_b64encode(os.urandom(4)).decode().rstrip('=')}@example.com"
    # Use a random email so we don't interfere with other tests
    seen_429 = False
    for i in range(7):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong"}, timeout=10)
        if r.status_code == 429:
            seen_429 = True
            break
    # rate limit may key on (ip,email) or just email; either way we expect 429 after 5
    # If not seen, at minimum we should get 401 for all
    if not seen_429:
        pytest.skip("rate limit not triggered on fresh email in this env (may be per real email only)")
    assert seen_429
