"""Tests for the new AI Document Explainer <-> Trust Draft linkage:
- POST /admin/trust-cases/{id}/admin-documents/from-trust-draft (import)
- DELETE /admin/trust-cases/{id}/trust-draft (delete)
"""
import io
import os
import time
import uuid
import pytest
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "https://trust-intake-portal.preview.emergentagent.com"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"


def _make_pdf_bytes(text: str = "Test Trust Draft Article I. Grantor establishes this Trust.") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "ARTICLE I - THE GRANTOR")
    c.drawString(72, 700, text)
    c.drawString(72, 680, "ARTICLE II - TRUSTEE POWERS")
    c.drawString(72, 660, "The Trustee shall administer the trust per this instrument.")
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


@pytest.fixture(scope="module")
def client_session():
    """Create a fresh client account so we can test non-admin auth on these endpoints."""
    s = requests.Session()
    email = f"tdtest_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "Client12345!", "name": "TD Tester"})
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return s


@pytest.fixture
def fresh_case(admin_session):
    """Create a fresh trust case via a fresh client, return case_id."""
    # Create a client
    cs = requests.Session()
    email = f"tdcase_{uuid.uuid4().hex[:8]}@example.com"
    r = cs.post(f"{API}/auth/register",
                json={"email": email, "password": "Client12345!", "name": "Case Owner"})
    assert r.status_code in (200, 201), r.text
    # Create case
    r = cs.post(f"{API}/trust-cases",
                json={"trust_name": f"TEST_TD_{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), r.text
    case_id = r.json().get("id") or r.json().get("case_id")
    assert case_id
    yield case_id
    # No teardown needed; cases are ephemeral test data


def _upload_draft(admin_session, case_id):
    pdf = _make_pdf_bytes()
    files = {"file": ("test-trust-draft.pdf", pdf, "application/pdf")}
    r = admin_session.post(f"{API}/admin/trust-cases/{case_id}/trust-draft", files=files)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    return r.json()


# ---------------------- IMPORT (from-trust-draft) ----------------------

class TestImportFromTrustDraft:
    def test_no_draft_returns_400(self, admin_session, fresh_case):
        r = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert "no trust draft" in detail, f"unexpected detail: {detail}"

    def test_unknown_case_returns_404(self, admin_session):
        r = admin_session.post(
            f"{API}/admin/trust-cases/does-not-exist-{uuid.uuid4().hex[:8]}/admin-documents/from-trust-draft")
        assert r.status_code == 404

    def test_requires_admin_auth_anon(self, anon_session, fresh_case):
        r = anon_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_requires_admin_auth_client(self, client_session, fresh_case):
        r = client_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_import_creates_admin_doc_with_ai_explanation(self, admin_session, fresh_case):
        draft = _upload_draft(admin_session, fresh_case)
        r = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["already_imported"] is False
        assert body["source"] == "trust_draft"
        assert body["source_storage_path"] == draft["storage_path"]
        assert body["source_draft_id"] == draft["id"]
        assert body["source_draft_version"] == draft["version"]
        assert body["label"].startswith("Trust Draft — ")
        assert isinstance(body.get("ai_explanation"), dict)
        # ai_explanation should be populated (not an empty stub)
        ai = body["ai_explanation"]
        assert ai, "ai_explanation is empty"
        # Verify persisted via GET
        r2 = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        assert r2.status_code == 200
        docs = r2.json().get("admin_documents") or []
        matching = [d for d in docs if d.get("source") == "trust_draft"]
        assert len(matching) == 1
        assert matching[0]["ai_explanation"]

    def test_import_is_idempotent(self, admin_session, fresh_case):
        _upload_draft(admin_session, fresh_case)
        r1 = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r1.status_code == 200
        assert r1.json()["already_imported"] is False
        first_id = r1.json()["id"]
        # Call again
        r2 = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r2.status_code == 200
        assert r2.json()["already_imported"] is True
        assert r2.json()["id"] == first_id
        # Verify only ONE trust_draft-source doc
        r3 = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        docs = r3.json().get("admin_documents") or []
        matching = [d for d in docs if d.get("source") == "trust_draft"]
        assert len(matching) == 1, f"expected 1, got {len(matching)}"


# ---------------------- DELETE trust-draft ----------------------

class TestDeleteTrustDraft:
    def test_no_draft_returns_400(self, admin_session, fresh_case):
        r = admin_session.delete(f"{API}/admin/trust-cases/{fresh_case}/trust-draft")
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert "no trust draft" in detail

    def test_unknown_case_returns_404(self, admin_session):
        r = admin_session.delete(
            f"{API}/admin/trust-cases/does-not-exist-{uuid.uuid4().hex[:8]}/trust-draft")
        assert r.status_code == 404

    def test_requires_admin_auth_anon(self, anon_session, fresh_case):
        r = anon_session.delete(f"{API}/admin/trust-cases/{fresh_case}/trust-draft")
        assert r.status_code in (401, 403)

    def test_requires_admin_auth_client(self, client_session, fresh_case):
        r = client_session.delete(f"{API}/admin/trust-cases/{fresh_case}/trust-draft")
        assert r.status_code in (401, 403)

    def test_delete_resets_case(self, admin_session, fresh_case):
        _upload_draft(admin_session, fresh_case)
        # Confirm draft + sections_draft exists (auto-extract may or may not have run)
        r_before = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        assert r_before.status_code == 200
        assert r_before.json().get("trust_draft") is not None

        r = admin_session.delete(f"{API}/admin/trust-cases/{fresh_case}/trust-draft")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"] is True

        r_after = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        assert r_after.status_code == 200
        case = r_after.json()
        assert case.get("trust_draft") in (None, {})
        assert case.get("trust_draft_deleted_at")
        assert case.get("trust_draft_deleted_by")
        assert case.get("trust_sections") == []
        assert case.get("trust_sections_draft") == []


# ---------------------- Combined workflow ----------------------

class TestCombinedWorkflow:
    def test_import_then_delete_preserves_explainer(self, admin_session, fresh_case):
        draft = _upload_draft(admin_session, fresh_case)
        # Import
        r = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents/from-trust-draft")
        assert r.status_code == 200
        imported_doc_id = r.json()["id"]
        # Delete trust_draft
        r_del = admin_session.delete(f"{API}/admin/trust-cases/{fresh_case}/trust-draft")
        assert r_del.status_code == 200
        # Verify explainer doc PERSISTS and is marked source_orphaned
        r_get = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        docs = r_get.json().get("admin_documents") or []
        matching = [d for d in docs if d.get("id") == imported_doc_id]
        assert len(matching) == 1, "imported explainer doc should still exist"
        assert matching[0].get("source_orphaned") is True, \
            f"expected source_orphaned=True, got {matching[0].get('source_orphaned')}"
        # AI explanation preserved
        assert matching[0].get("ai_explanation")


# ---------------------- Regression ----------------------

class TestRegressionUploadEndpoints:
    def test_regular_admin_document_upload_still_works(self, admin_session, fresh_case):
        pdf = _make_pdf_bytes("Regular upload smoke test")
        files = {"file": ("misc.pdf", pdf, "application/pdf")}
        data = {"label": "TEST_REG_UPLOAD"}
        r = admin_session.post(
            f"{API}/admin/trust-cases/{fresh_case}/admin-documents",
            files=files, data=data)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("label") == "TEST_REG_UPLOAD"
        assert body.get("source") is None  # regular uploads don't set source

    def test_get_case_shape_intact(self, admin_session, fresh_case):
        r = admin_session.get(f"{API}/admin/trust-cases/{fresh_case}")
        assert r.status_code == 200
        case = r.json()
        assert "id" in case
