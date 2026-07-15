"""Tests for the page-by-page trust explanation background job feature.

Verifies:
  - GET /api/trust-cases/{id}/trust-page-explanations returns schema + status
  - Anonymous access returns 401
  - Admin regenerate re-fires the job (200) and 400 with no draft
  - No banned legal jargon in explanations
  - Personalization: mentions Michael / Sarah / James
  - Regression: single-explanation endpoint still returns personalized content
  - Regression: extract-status endpoint still works
"""
import os
import io
import time
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"
SEEDED_CASE_ID = "8eb42bd3-5d43-43f2-b765-b98a144bd931"

BANNED = ["settlor", "per stirpes", "corpus", "in terrorem",
          "spendthrift", "hereinafter", "aforementioned"]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ---- Anon must be 401 ----
def test_anon_get_page_explanations_401():
    r = requests.get(
        f"{BASE_URL}/api/trust-cases/{SEEDED_CASE_ID}/trust-page-explanations",
        timeout=15,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


# ---- Schema & personalization ----
def test_get_page_explanations_schema_and_personalization(admin_session):
    # Poll up to ~4 min waiting for completion (LLM ~30s per batch of 2 pages)
    deadline = time.time() + 240
    last = None
    while time.time() < deadline:
        r = admin_session.get(
            f"{BASE_URL}/api/trust-cases/{SEEDED_CASE_ID}/trust-page-explanations",
            timeout=30,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        last = r.json()
        # Required schema keys
        for k in ("ok", "explanations", "status", "pages_done",
                  "pages_total", "batches_done", "batches_total"):
            assert k in last, f"missing key {k}: {last.keys()}"
        assert isinstance(last["explanations"], list)
        assert last["status"] in ("pending", "completed", "failed", "idle")
        if last["status"] == "completed" and last["explanations"]:
            break
        if last["status"] == "failed":
            pytest.fail(f"job failed: {last.get('error')}")
        time.sleep(6)
    assert last and last["status"] == "completed", f"timed out — last={last}"
    assert last["pages_total"] >= 1
    assert len(last["explanations"]) == last["pages_total"], \
        f"expected {last['pages_total']} explanations, got {len(last['explanations'])}"

    # Each entry has page(int) + text(html-ish str)
    pages_seen = set()
    joined = ""
    for e in last["explanations"]:
        assert isinstance(e.get("page"), int)
        assert isinstance(e.get("text"), str) and e["text"].strip()
        pages_seen.add(e["page"])
        joined += "\n" + e["text"]
    assert pages_seen == set(range(1, last["pages_total"] + 1))

    # Banned jargon check
    low = joined.lower()
    hits = [b for b in BANNED if b in low]
    assert not hits, f"banned jargon found: {hits}"

    # Personalization — case is Michael Thompson w/ Sarah/James beneficiaries
    for name in ("Michael", "Sarah", "James"):
        assert name in joined, f"personalization missing name '{name}'"


# ---- Regenerate on seeded case (has a draft) ----
def test_regenerate_success(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{SEEDED_CASE_ID}"
        f"/trust-page-explanations/regenerate",
        timeout=30,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert data.get("ok") is True
    assert "task_id" in data
    assert data.get("status") in ("pending", "completed")


# ---- Regenerate fails with 400 when no trust draft ----
def test_regenerate_no_draft_returns_400(admin_session):
    # Find an existing case with no trust_draft
    r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases", timeout=90)
    assert r.status_code == 200
    cases = r.json() if isinstance(r.json(), list) else r.json().get("cases", [])
    target = None
    for c in cases:
        if not c.get("trust_draft") and c.get("id") != SEEDED_CASE_ID:
            target = c["id"]
            break
    if not target:
        pytest.skip("no existing case without a trust_draft available")
    rr = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{target}"
        f"/trust-page-explanations/regenerate",
        timeout=30,
    )
    assert rr.status_code == 400, f"expected 400 got {rr.status_code}: {rr.text[:200]}"


# ---- Regression: single-explanation endpoint still personalized ----
def test_single_explanation_regression(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/trust-cases/{SEEDED_CASE_ID}/trust-draft-explanation",
        timeout=90,
    )
    # 200 if a prior iteration already imported a trust_draft admin_document; 404 acceptable.
    if r.status_code == 404:
        pytest.skip("Single-explanation not yet generated for this case (prior iterations).")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    body = r.json()
    text_blob = str(body)
    assert "Michael" in text_blob


# ---- Regression: extract-status ----
def test_extract_status_regression(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/admin/trust-cases/{SEEDED_CASE_ID}"
        f"/trust-sections/extract-status",
        timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"


# ---- Server is up (startup sweep didn't crash it) ----
def test_server_alive_after_startup_sweep():
    r = requests.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
