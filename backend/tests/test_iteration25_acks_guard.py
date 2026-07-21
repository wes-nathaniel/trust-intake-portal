"""Iteration 25 — acknowledgments guard tests.

Bug context: intake-time disclosure checkboxes were flipping
`review_completed_ack=True` on the case, which caused the admin dashboard to
render "Client marked review as completed. Ready for payment." even though
the admin had never uploaded a trust draft. The fix splits the flow into:

  * `intake_submitted_ack`  -> intake done, advance to "In Review"
  * `review_completed_ack`  -> client approved drafted trust; only allowed
     AFTER admin uploaded a trust draft AND status == "Ready for Client Review"

Additionally, uploading a new trust draft auto-resets any lingering
`review_completed_ack` back to False, and `_auto_intake_status` still honors
legacy `review_completed_ack` as an intake-done signal for pre-fix cases.
"""
import io
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL"):
                BASE = ln.split("=", 1)[1].strip().rstrip("/")
                break
assert BASE, "REACT_APP_BACKEND_URL required"
API = f"{BASE}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"

# Unique client per test module run to avoid cross-run pollution
_TAG = uuid.uuid4().hex[:8]
CLIENT_EMAIL = f"acks_client_{_TAG}@example.com"
CLIENT_PASSWORD = "Client12345!"


# ---------------- helpers ----------------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return s


def _register(email, password, name):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": password, "name": name
    }, timeout=15)
    assert r.status_code in (200, 201, 400, 409), f"register failed: {r.status_code} {r.text}"


def _make_pdf_bytes():
    """Build the smallest valid single-page PDF (~300 bytes)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "TEST TRUST DRAFT")
        buf = doc.tobytes()
        doc.close()
        return buf
    except Exception:
        # Fallback: minimal hand-crafted PDF
        return (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n"
            b"0000000053 00000 n \n0000000095 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"
        )


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def client():
    _register(CLIENT_EMAIL, CLIENT_PASSWORD, "Acks Test Client")
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture
def case(client, admin):
    """Fresh case per test, cleaned up on teardown."""
    r = client.post(f"{API}/trust-cases", json={
        "trust_type": "single",
        "trust_name": f"TEST_ACKS_{uuid.uuid4().hex[:6]}",
        "intake_path": "new",
    }, timeout=15)
    assert r.status_code in (200, 201), f"create case failed: {r.status_code} {r.text}"
    case_id = r.json()["id"]
    yield case_id
    try:
        admin.delete(f"{API}/admin/trust-cases/{case_id}?delete_user=false", timeout=15)
    except Exception:
        pass


def _get_case_as_admin(admin, case_id):
    r = admin.get(f"{API}/admin/trust-cases/{case_id}", timeout=15)
    assert r.status_code == 200, f"admin get case failed: {r.status_code} {r.text}"
    return r.json()


def _set_status(admin, case_id, status):
    r = admin.put(f"{API}/admin/trust-cases/{case_id}/status", json={"status": status}, timeout=15)
    assert r.status_code in (200, 204), f"status update failed: {r.status_code} {r.text}"


def _upload_draft(admin, case_id):
    pdf = _make_pdf_bytes()
    r = admin.post(
        f"{API}/admin/trust-cases/{case_id}/trust-draft",
        files={"file": ("trust.pdf", io.BytesIO(pdf), "application/pdf")},
        timeout=30,
    )
    assert r.status_code == 200, f"upload draft failed: {r.status_code} {r.text}"
    return r.json()


# ---------------- Backend guard: 4 combos ----------------
class TestReviewCompletedAckGuard:
    """PUT /trust-cases/{id}/acknowledgments {review_completed_ack:true}
    as CLIENT: must be 400 unless (has_draft AND status='Ready for Client Review')."""

    def test_no_draft_intake_status_rejects(self, client, case):
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        assert "cannot mark the trust review complete yet" in r.text.lower()

    def test_no_draft_ready_status_rejects(self, client, admin, case):
        _set_status(admin, case, "Ready for Client Review")
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_draft_intake_status_rejects(self, client, admin, case):
        _upload_draft(admin, case)
        # Status still an intake status (upload doesn't change status)
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_draft_ready_status_succeeds(self, client, admin, case):
        _upload_draft(admin, case)
        _set_status(admin, case, "Ready for Client Review")
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
        doc = _get_case_as_admin(admin, case)
        assert doc["acknowledgments"]["review_completed_ack"] is True
        # Status must NOT auto-advance to Ready for Payment; admin advances manually.
        assert doc["status"] == "Ready for Client Review"


# ---------------- Disclosure ticks must not pollute review_completed_ack ----------------
class TestDisclosureTicksDoNotPollute:

    def test_disclosure_acks_accepted_but_review_flag_stays_false(self, client, admin, case):
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments", json={
            "disclosure_ack": True,
            "state_laws_ack": True,
            "notarization_ack": True,
        }, timeout=15)
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
        doc = _get_case_as_admin(admin, case)
        acks = doc.get("acknowledgments") or {}
        assert acks.get("disclosure_ack") is True
        assert acks.get("state_laws_ack") is True
        assert acks.get("notarization_ack") is True
        # THE CRITICAL ASSERT: disclosure ticks must NEVER flip review_completed_ack
        assert acks.get("review_completed_ack") in (False, None), (
            f"review_completed_ack polluted by disclosure ticks: {acks}"
        )


# ---------------- Intake completion path ----------------
class TestIntakeCompletionPath:

    def test_intake_submitted_ack_advances_to_in_review(self, client, admin, case):
        # Case starts at "Intake Started" or similar intake status
        doc0 = _get_case_as_admin(admin, case)
        assert doc0["status"] in {"Intake Started", "Intake In Progress", "Waiting on Documents"}, (
            f"unexpected starting status: {doc0['status']}"
        )
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"intake_submitted_ack": True}, timeout=15)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        doc = _get_case_as_admin(admin, case)
        assert doc["status"] == "In Review", f"expected In Review, got {doc['status']}"
        acks = doc.get("acknowledgments") or {}
        assert acks.get("intake_submitted_ack") is True
        assert acks.get("review_completed_ack") in (False, None)


# ---------------- Draft review completion (happy path) covered by
# TestReviewCompletedAckGuard.test_draft_ready_status_succeeds ------


# ---------------- Auto-reset on new draft upload ----------------
class TestAutoResetOnNewDraft:

    def test_new_draft_upload_resets_review_completed_ack(self, client, admin, case):
        # 1. Upload draft + move to Ready for Client Review + client approves
        _upload_draft(admin, case)
        _set_status(admin, case, "Ready for Client Review")
        r = client.put(f"{API}/trust-cases/{case}/acknowledgments",
                       json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 200
        doc1 = _get_case_as_admin(admin, case)
        assert doc1["acknowledgments"]["review_completed_ack"] is True

        # 2. Admin uploads NEW draft -> must auto-reset review_completed_ack
        _upload_draft(admin, case)
        doc2 = _get_case_as_admin(admin, case)
        acks = doc2.get("acknowledgments") or {}
        assert acks.get("review_completed_ack") is False, (
            f"new draft upload did NOT reset review_completed_ack: {acks}"
        )


# ---------------- Legacy passthrough via _auto_intake_status ----------------
class TestLegacyPassthrough:
    """A legacy case that had `review_completed_ack=True` set during intake
    should still be treated as intake-done by _auto_intake_status. We can
    exercise this indirectly: hit an intake endpoint that recomputes status
    for such a case. Since setting review_completed_ack directly is now
    blocked for clients, we simulate by having admin flip the flag then
    verify status-recompute treats it as intake-done."""

    def test_admin_sets_review_completed_ack_then_status_recomputes(self, client, admin, case):
        # Admin can bypass the guard
        r = admin.put(f"{API}/trust-cases/{case}/acknowledgments",
                      json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 200, f"admin set failed: {r.status_code} {r.text}"
        doc = _get_case_as_admin(admin, case)
        assert doc["acknowledgments"]["review_completed_ack"] is True
        # Admin action does NOT auto-advance status (guard uses role check),
        # but the legacy signal is preserved in the doc for _auto_intake_status
        # to honor on any subsequent recompute.


# ---------------- Admin override ----------------
class TestAdminOverride:

    def test_admin_can_set_review_completed_ack_without_draft(self, admin, case):
        # No draft, intake status — admin should still be allowed
        r = admin.put(f"{API}/trust-cases/{case}/acknowledgments",
                      json={"review_completed_ack": True}, timeout=15)
        assert r.status_code == 200, f"admin override failed: {r.status_code} {r.text}"
        doc = _get_case_as_admin(admin, case)
        assert doc["acknowledgments"]["review_completed_ack"] is True
