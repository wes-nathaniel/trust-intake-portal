"""Background auto-extract tests for trust-sections.

Covers:
- POST /api/admin/trust-cases/{case_id}/trust-sections/auto-extract returns 202 fast
- Duplicate calls return already_running=true with same task_id
- Case without draft returns 400
- Unknown case returns 404
- Unauthenticated returns 401/403
- GET extract-status transitions pending -> completed/failed
- Inline path: uploading trust_draft returns quickly and kicks off background job
- Case doc mirrors trust_extract_job
"""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://trust-intake-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"


def _build_multi_article_pdf() -> bytes:
    """Build a multi-article trust PDF that trust_extractor can split."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    articles = [
        ("ARTICLE I — Declaration of Trust",
         "The Grantor hereby declares that the Trustee holds property in trust "
         "for the beneficiaries. This Article establishes the trust corpus and "
         "confirms the Grantor's intent to create a valid revocable living trust."),
        ("ARTICLE II — Trustee Powers",
         "The Trustee shall have all powers necessary to administer the trust, "
         "including the power to invest, sell, lease, and distribute trust assets "
         "in the best interests of the beneficiaries under the prudent investor rule."),
        ("ARTICLE III — Distributions",
         "During the Grantor's lifetime, income and principal may be distributed "
         "to the Grantor upon request. Upon death, remaining assets shall pass "
         "per stirpes to the Grantor's descendants."),
        ("ARTICLE IV — Successor Trustee",
         "If the initial Trustee cannot serve, the named Successor Trustee shall "
         "assume all duties without court order. The Successor Trustee shall "
         "provide accountings annually to qualified beneficiaries."),
    ]
    y = 750
    for title, body in articles:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, title)
        y -= 20
        c.setFont("Helvetica", 10)
        # naive wrap
        words = body.split()
        line = ""
        for w in words:
            if len(line) + len(w) > 90:
                c.drawString(72, y, line)
                y -= 14
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            c.drawString(72, y, line)
            y -= 30
        if y < 100:
            c.showPage(); y = 750
    c.save()
    return buf.getvalue()


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
    email = f"testclient_ae_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "AE Test"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def case_no_draft(client_session):
    r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
    assert r.status_code == 200
    return r.json()["id"]


@pytest.fixture(scope="module")
def multi_article_pdf():
    return _build_multi_article_pdf()


# ---------- TESTS ----------

class TestAutoExtractEndpoint:

    def test_unauthenticated_rejected(self, case_no_draft):
        r = requests.post(
            f"{API}/admin/trust-cases/{case_no_draft}/trust-sections/auto-extract"
        )
        assert r.status_code in (401, 403), r.text

    def test_unknown_case_404(self, admin_session):
        fake = uuid.uuid4().hex
        r = admin_session.post(f"{API}/admin/trust-cases/{fake}/trust-sections/auto-extract")
        assert r.status_code == 404

    def test_no_draft_returns_400(self, admin_session, case_no_draft):
        r = admin_session.post(
            f"{API}/admin/trust-cases/{case_no_draft}/trust-sections/auto-extract"
        )
        assert r.status_code == 400
        assert "trust draft" in r.json().get("detail", "").lower()

    def test_status_idle_when_never_run(self, admin_session, case_no_draft):
        r = admin_session.get(
            f"{API}/admin/trust-cases/{case_no_draft}/trust-sections/extract-status"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "idle"
        assert data["sections_count"] == 0

    def test_status_fresh_case_no_draft_field_returns_idle_200(self, admin_session, client_session):
        """BUG FIX 1 regression: fresh case with NO trust_sections_draft field at all
        must return 200 idle, not 404. Previously failed because projection returned
        an empty dict which was treated as falsy."""
        # Create a brand-new case (guaranteed to have no trust_extract_job and no
        # trust_sections_draft fields on the document).
        cr = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert cr.status_code == 200
        cid = cr.json()["id"]
        r = admin_session.get(
            f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status"
        )
        assert r.status_code == 200, f"Expected 200 idle, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["status"] == "idle"
        assert data["sections_count"] == 0
        assert "message" in data

    def test_status_unknown_case_still_404(self, admin_session):
        """BUG FIX 1: ensure the fix didn't accidentally make truly-unknown cases
        return 200 idle."""
        fake = uuid.uuid4().hex
        r = admin_session.get(
            f"{API}/admin/trust-cases/{fake}/trust-sections/extract-status"
        )
        assert r.status_code == 404


class TestUploadPerf:
    """BUG FIX 2: upload should return in <3s (previously ~30s due to blocking email)."""

    def test_upload_returns_under_3s(self, admin_session, client_session, multi_article_pdf):
        cr = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert cr.status_code == 200
        cid = cr.json()["id"]

        t0 = time.time()
        up = admin_session.post(
            f"{API}/admin/trust-cases/{cid}/trust-draft",
            files={"file": ("trust_perf.pdf", multi_article_pdf, "application/pdf")},
        )
        dt = time.time() - t0
        assert up.status_code == 200, up.text
        assert dt < 3.0, f"Upload took {dt:.2f}s — must be < 3s after fix"
        print(f"Upload completed in {dt:.2f}s")

        # trust_draft persisted
        case_r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        assert case_r.status_code == 200
        case = case_r.json()
        assert case.get("trust_draft") or case.get("trust_draft_filename"), \
            "trust_draft not persisted"

        # Background extract job kicked off
        st = admin_session.get(
            f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status"
        ).json()
        assert st.get("status") in ("pending", "completed", "failed"), \
            f"Background job not kicked off: {st}"


class TestAutoExtractBackground:
    """End-to-end: upload multi-article PDF, verify 202-fast, poll status."""

    @pytest.fixture(scope="class")
    def case_with_draft(self, admin_session, client_session, multi_article_pdf):
        # create a case
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert r.status_code == 200
        cid = r.json()["id"]

        # upload the multi-article PDF (this ALSO kicks off inline background job)
        t0 = time.time()
        up = admin_session.post(
            f"{API}/admin/trust-cases/{cid}/trust-draft",
            files={"file": ("trust_multi.pdf", multi_article_pdf, "application/pdf")},
        )
        upload_dt = time.time() - t0
        assert up.status_code == 200, up.text
        # Inline upload path must NOT block on Claude (used to hang >60s).
        # Warn on anything slower than 15s (likely email/notify overhead).
        if upload_dt >= 15:
            print(f"WARN: upload took {upload_dt:.1f}s (target < 15s). "
                  f"Slow but not blocking on Claude.")
        assert upload_dt < 60, f"Upload took {upload_dt:.1f}s — MUST not block on Claude"
        return cid, upload_dt

    def test_inline_upload_returns_fast(self, case_with_draft):
        cid, dt = case_with_draft
        # Non-blocking check only. Actual perf concern reported to main agent.
        assert dt < 60

    def test_inline_kicks_off_job(self, admin_session, case_with_draft):
        cid, _ = case_with_draft
        # Poll — should show a job in flight (pending) or already completed
        r = admin_session.get(
            f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status"
        )
        assert r.status_code == 200
        data = r.json()
        # Either pending, completed, or failed — but NOT idle since inline path ran
        assert data.get("status") in ("pending", "completed", "failed"), data
        assert "task_id" in data

    def test_explicit_autoextract_returns_202_fast(self, admin_session, case_with_draft):
        cid, _ = case_with_draft
        t0 = time.time()
        r = admin_session.post(
            f"{API}/admin/trust-cases/{cid}/trust-sections/auto-extract"
        )
        dt = time.time() - t0
        assert r.status_code == 202, r.text
        assert dt < 5, f"POST took {dt:.1f}s — must be non-blocking"
        body = r.json()
        assert body["ok"] is True
        assert "task_id" in body
        assert body["status"] in ("pending", "completed")

    def test_duplicate_call_returns_same_task(self, admin_session, case_with_draft):
        cid, _ = case_with_draft
        r1 = admin_session.post(
            f"{API}/admin/trust-cases/{cid}/trust-sections/auto-extract"
        )
        assert r1.status_code == 202
        b1 = r1.json()
        tid1 = b1["task_id"]
        # Immediate second call
        r2 = admin_session.post(
            f"{API}/admin/trust-cases/{cid}/trust-sections/auto-extract"
        )
        assert r2.status_code == 202
        body2 = r2.json()
        # Only meaningful if job1 was still pending — dedupe should kick in.
        if b1["status"] == "pending":
            # Poll status right now to confirm pending
            st = admin_session.get(
                f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status"
            ).json()
            if st.get("status") == "pending":
                assert body2.get("already_running") is True
                assert body2["task_id"] == tid1
            else:
                print(f"Job completed between calls: {st.get('status')}")
        else:
            print(f"Initial call was already {b1['status']} — dedupe N/A")

    def test_status_transitions_to_terminal(self, admin_session, case_with_draft):
        cid, _ = case_with_draft
        deadline = time.time() + 180  # 3 min
        last = None
        while time.time() < deadline:
            r = admin_session.get(
                f"{API}/admin/trust-cases/{cid}/trust-sections/extract-status"
            )
            assert r.status_code == 200
            last = r.json()
            if last["status"] in ("completed", "failed"):
                break
            time.sleep(6)
        assert last is not None
        print(f"Final status: {last}")
        assert last["status"] in ("completed", "failed"), f"Never terminated: {last}"

        if last["status"] == "completed":
            # Sections must have been populated in draft slot
            case_r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
            assert case_r.status_code == 200
            case = case_r.json()
            draft_sections = case.get("trust_sections_draft") or []
            assert len(draft_sections) >= 1, "trust_sections_draft empty after success"
            assert case.get("trust_sections_draft_created_at")
            # Job mirrored on case doc
            assert case.get("trust_extract_job", {}).get("status") == "completed"
        else:
            # failed — error msg should be present
            assert last.get("error"), "failed status missing error message"

    def test_publish_and_delete_regression(self, admin_session, case_with_draft):
        """Regression: publish-draft still works, delete trust-draft still works."""
        cid, _ = case_with_draft
        # Get current state
        case_r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        draft = case_r.json().get("trust_sections_draft") or []
        if draft:
            r = admin_session.post(
                f"{API}/admin/trust-cases/{cid}/trust-sections/publish-draft"
            )
            assert r.status_code == 200
            assert r.json()["published"] is True
            # verify promotion
            case_r2 = admin_session.get(f"{API}/admin/trust-cases/{cid}")
            case2 = case_r2.json()
            assert len(case2.get("trust_sections") or []) >= 1
            assert (case2.get("trust_sections_draft") or []) == []

        # DELETE trust draft — must succeed and clear draft
        d = admin_session.delete(f"{API}/admin/trust-cases/{cid}/trust-draft")
        assert d.status_code == 200, d.text
        case_r3 = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        case3 = case_r3.json()
        assert (case3.get("trust_sections_draft") or []) == []
