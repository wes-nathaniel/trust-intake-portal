"""Iteration 17 — Personalized trust-draft AI explanation tests.

Tests the new personalization flow:
  * POST /admin/trust-cases/{id}/admin-documents/from-trust-draft passes case_context
  * GET  /trust-cases/{id}/trust-draft-explanation (client endpoint)
  * Regenerate keeps personalization for trust_draft source docs
  * Regular admin-doc upload still yields legacy (non-personalized) explanation
  * Idempotency of from-trust-draft
"""
import os
import io
import json
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
CASE_ID = "8eb42bd3-5d43-43f2-b765-b98a144bd931"
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"

PERSONAL_KEYS = [
    "greeting",
    "grantor_intro",
    "trustee_roles",
    "beneficiaries",
    "assets_plain",
    "trust_type_meaning",
    "next_steps",
]
LEGACY_KEYS = ["what_is", "what_it_does", "why_it_matters", "notarization", "client_action"]
JARGON = ["per stirpes", "settlor", "corpus", "in terrorem"]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def _get_case(session):
    r = session.get(f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# --- Idempotency + shape ---
def test_from_trust_draft_endpoint_returns_personalized_ai(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=180,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    ai = body.get("ai_explanation") or {}
    assert ai.get("personalized") is True, f"expected personalized=true, got {ai.get('personalized')}"
    for k in PERSONAL_KEYS:
        v = ai.get(k)
        assert isinstance(v, str) and v.strip(), f"personal field '{k}' empty: {v!r}"
    for k in LEGACY_KEYS:
        assert k in ai, f"legacy compat field missing: {k}"


def test_from_trust_draft_content_includes_michael_sarah_james(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=180,
    )
    assert r.status_code == 200, r.text
    ai = r.json().get("ai_explanation") or {}
    blob = " ".join(str(ai.get(k, "")) for k in PERSONAL_KEYS).lower()
    for needle in ["michael", "sarah", "james", "60%", "40%", "fidelity"]:
        assert needle.lower() in blob, f"missing '{needle}' in personalized explanation"
    # address: at least one of these should appear
    assert ("123 maple" in blob) or ("fort lauderdale" in blob), \
        "expected home address (123 Maple or Fort Lauderdale) in explanation"
    for j in JARGON:
        assert j.lower() not in blob, f"legal jargon '{j}' should NOT appear in plain-English text"


def test_from_trust_draft_is_idempotent(admin_session):
    r1 = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=180,
    )
    assert r1.status_code == 200
    before = len([d for d in (_get_case(admin_session).get("admin_documents") or [])
                  if d.get("source") == "trust_draft" and not d.get("is_deleted")])
    r2 = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=60,
    )
    assert r2.status_code == 200
    assert r2.json().get("already_imported") is True, "second call must be idempotent"
    after = len([d for d in (_get_case(admin_session).get("admin_documents") or [])
                 if d.get("source") == "trust_draft" and not d.get("is_deleted")])
    assert before == after, f"admin_documents count changed on repeat call ({before}->{after})"


# --- Client-facing GET endpoint ---
def test_client_trust_draft_explanation_returns_personalized(admin_session):
    # ensure exists
    admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=180,
    )
    r = admin_session.get(f"{BASE_URL}/api/trust-cases/{CASE_ID}/trust-draft-explanation", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("personalized") is True
    assert body.get("label")
    ai = body.get("explanation") or {}
    for k in PERSONAL_KEYS:
        assert ai.get(k), f"client endpoint missing personal field {k}"


def test_client_endpoint_requires_auth():
    r = requests.get(f"{BASE_URL}/api/trust-cases/{CASE_ID}/trust-draft-explanation", timeout=15)
    assert r.status_code in (401, 403), f"expected auth-required, got {r.status_code}"


def test_client_endpoint_returns_404_when_no_draft_doc(admin_session):
    # Case with no trust_draft admin_document — create a temporary empty case.
    r = admin_session.post(
        f"{BASE_URL}/api/trust-cases",
        json={"client_name": "TEST_NoDraft", "client_email": "test_nodraft@example.com"},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot create test case: {r.status_code} {r.text[:200]}")
    new_case_id = r.json().get("id") or r.json().get("case_id")
    if not new_case_id:
        pytest.skip("no case id in create response")
    try:
        g = admin_session.get(
            f"{BASE_URL}/api/trust-cases/{new_case_id}/trust-draft-explanation", timeout=15)
        assert g.status_code == 404
        detail = (g.json() or {}).get("detail", "")
        assert "not been generated" in detail.lower() or "not been" in detail.lower(), \
            f"unexpected 404 body: {detail}"
    finally:
        admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{new_case_id}", timeout=15)


# --- Regenerate keeps personalization ---
def test_regenerate_trust_draft_doc_stays_personalized(admin_session):
    admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/from-trust-draft",
        timeout=180,
    )
    case = _get_case(admin_session)
    doc = next((d for d in (case.get("admin_documents") or [])
                if d.get("source") == "trust_draft" and not d.get("is_deleted")), None)
    assert doc, "no trust_draft admin_document found to regenerate"
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/{doc['id']}/regenerate",
        timeout=180,
    )
    assert r.status_code == 200, r.text
    ai = (r.json() or {}).get("ai_explanation") or {}
    assert ai.get("personalized") is True, "regenerate on trust_draft source must produce personalized AI"
    for k in PERSONAL_KEYS:
        assert ai.get(k), f"regenerate missing {k}"


# --- Regular non-trust-draft upload is still legacy ---
def test_regular_upload_produces_legacy_explanation(admin_session):
    # tiny text file so LLM still runs quickly
    content = (b"Operating Agreement of TEST LLC. Member: Michael Thompson. "
               b"This agreement governs the internal affairs of the LLC. ") * 4
    files = {"file": ("op_agreement.txt", io.BytesIO(content), "text/plain")}
    data = {"label": "TEST_OpAgreement"}
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents",
        files=files, data=data, timeout=180,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ai = body.get("ai_explanation") or {}
    assert ai.get("personalized") is not True, f"regular upload should be non-personalized: {ai.get('personalized')}"
    for k in LEGACY_KEYS:
        assert ai.get(k), f"legacy field '{k}' missing from regular upload"
    # cleanup
    doc_id = body.get("id")
    if doc_id:
        admin_session.delete(
            f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}/admin-documents/{doc_id}",
            timeout=30,
        )
