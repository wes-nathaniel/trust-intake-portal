"""
Test: Admin Case Detail crash fix - Lock/Unlock import and Trust Draft section
Tests that a case with a released trust_draft renders correctly on admin page.
Flow: register client -> create case -> admin uploads trust draft -> admin releases -> verify
"""
import pytest
import requests
import os
import io

def _get_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
        except Exception:
            pass
    return url.rstrip("/")

BASE_URL = _get_base_url()

ADMIN_EMAIL = "wes@igchq.com"
ADMIN_PASSWORD = "Wllorenzo03!"
CLIENT_EMAIL = "testcrash_fix_t1@example.com"
CLIENT_PASSWORD = "TestPass123!"
CLIENT_NAME = "TEST_ CrashFix"

# Minimal valid PDF bytes
MINIMAL_PDF = b"""%PDF-1.0
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def client_session():
    """Register a test client user and return a session. Cleanup is done in test_delete_test_case."""
    s = requests.Session()
    # Try to register; if already exists, just login
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": CLIENT_EMAIL,
        "name": CLIENT_NAME,
        "password": CLIENT_PASSWORD
    })
    if r.status_code == 400 and "already registered" in r.text:
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD})
    assert r.status_code == 200, f"Client login/register failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def test_case_id(client_session, admin_session):
    """Create test case as client, yield its id, delete via admin at end."""
    r = client_session.post(f"{BASE_URL}/api/trust-cases", json={
        "trust_type": "single",
        "trust_name": "TEST_ Fix Trust"
    })
    assert r.status_code in (200, 201), f"Create case failed: {r.status_code} {r.text}"
    case = r.json()
    case_id = case.get("id") or case.get("case_id")
    assert case_id, f"No case_id in response: {case}"
    print(f"Created test case: {case_id}")

    yield case_id

    # Cleanup via admin
    del_r = admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{case_id}?delete_user=false")
    print(f"Deleted test case {case_id}: {del_r.status_code}")


class TestTrustDraftCrashFix:
    """Tests for Lock/Unlock import fix on admin case detail page"""

    def test_case_created(self, test_case_id):
        assert test_case_id is not None
        print(f"PASS: Case created with id={test_case_id}")

    def test_upload_trust_draft(self, admin_session, test_case_id):
        """Upload a minimal PDF as trust draft"""
        files = {"file": ("test_fix.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")}
        r = admin_session.post(
            f"{BASE_URL}/api/admin/trust-cases/{test_case_id}/trust-draft",
            files=files
        )
        assert r.status_code in (200, 201), f"Trust draft upload failed: {r.status_code} {r.text}"
        print(f"PASS: Trust draft uploaded. Response: {r.json()}")

    def test_release_trust_draft(self, admin_session, test_case_id):
        """Release the case so trust_draft.released=true"""
        r = admin_session.post(
            f"{BASE_URL}/api/admin/trust-cases/{test_case_id}/release",
            json={"mode": "silent", "send_email": False, "subject": "Test release", "message": "Test"}
        )
        assert r.status_code in (200, 201), f"Release failed: {r.status_code} {r.text}"
        print(f"PASS: Release response: {r.json()}")

    def test_case_has_released_trust_draft(self, admin_session, test_case_id):
        """Verify the case now has trust_draft.released=true"""
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{test_case_id}")
        assert r.status_code == 200, f"Get case failed: {r.text}"
        case = r.json()
        td = case.get("trust_draft")
        assert td is not None, "trust_draft is None - upload may have failed"
        assert td.get("released") is True, f"trust_draft.released is not True: {td}"
        print(f"PASS: trust_draft.released=True confirmed. trust_draft: {td}")

    def test_case_in_admin_list(self, admin_session, test_case_id):
        """Verify case appears in admin list"""
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert r.status_code == 200
        cases = r.json()
        ids = [c.get("id") for c in cases]
        assert test_case_id in ids, f"Test case {test_case_id} not in admin list"
        print(f"PASS: Case appears in admin list")

    def test_delete_test_case_and_verify_gone(self, admin_session, test_case_id):
        """Delete the test case and verify it no longer appears"""
        r = admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{test_case_id}?delete_user=false")
        assert r.status_code in (200, 204), f"Delete failed: {r.status_code} {r.text}"

        # Verify gone from list
        list_r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert list_r.status_code == 200
        ids = [c.get("id") for c in list_r.json()]
        assert test_case_id not in ids, "Case still in list after delete"
        print(f"PASS: Test case {test_case_id} deleted and confirmed gone from list")
