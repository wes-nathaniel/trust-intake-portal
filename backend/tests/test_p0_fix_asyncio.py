"""
P0 fix regression tests: asyncio.to_thread wrapping for get_object() calls
Tests: client doc download, admin doc download, trust preview meta, trust preview page PNG
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

ADMIN_EMAIL = "wes@igchq.com"
ADMIN_PASSWORD = "Wllorenzo03!"

# Test case IDs from review_request
TRUST_PREVIEW_CASE_ID = "562399a8-0b93-4e0d-9e8b-b6fd829af9ef"
CLIENT_DOC_CASE_ID = "6f96b5b7-084e-43df-af66-aa2022f1417d"
CLIENT_DOC_ID = "ae64a3cc-719c-44d2-a56d-d58d0e910171"
ADMIN_DOC_CASE_ID = "6f96b5b7-084e-43df-af66-aa2022f1417d"
ADMIN_DOC_ID = "e5383329-1be2-4a67-b180-c550a238c8c3"


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session using cookie-based auth"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text[:200]}")
    return session


class TestAdminDashboard:
    """Admin can log in and dashboard loads"""

    def test_admin_login(self):
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.text[:200]}"
        data = resp.json()
        assert "user" in data or "token" in data or "email" in data or resp.status_code == 200

    def test_trust_cases_list(self, admin_session):
        """Dashboard loads trust cases list"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert resp.status_code == 200, f"Trust cases list failed: {resp.text[:300]}"
        data = resp.json()
        assert isinstance(data, list) or isinstance(data, dict)


class TestTrustPreview:
    """Trust preview endpoints - P0 fix validation"""

    def test_trust_preview_meta(self, admin_session):
        """Trust preview meta returns 200 with pages > 0"""
        resp = admin_session.get(f"{BASE_URL}/api/trust-cases/{TRUST_PREVIEW_CASE_ID}/trust-preview/meta")
        assert resp.status_code == 200, f"Meta failed: {resp.status_code} {resp.text[:300]}"
        data = resp.json()
        assert "pages" in data or "total_pages" in data or "page_count" in data, f"No pages field: {data}"
        pages_val = data.get("pages") or data.get("total_pages") or data.get("page_count", 0)
        assert pages_val > 0, f"Pages should be > 0, got {pages_val}"
        print(f"Trust preview pages: {pages_val}")

    def test_trust_preview_page1_png(self, admin_session):
        """Trust preview page 1 PNG returns 200 with image content"""
        resp = admin_session.get(f"{BASE_URL}/api/trust-cases/{TRUST_PREVIEW_CASE_ID}/trust-preview/page/1.png")
        assert resp.status_code == 200, f"Page PNG failed: {resp.status_code} {resp.text[:300]}"
        assert len(resp.content) > 1000, "PNG content too small, likely empty"
        # Check content type is image
        content_type = resp.headers.get("content-type", "")
        assert "image" in content_type or "octet-stream" in content_type, f"Unexpected content type: {content_type}"
        print(f"Page 1 PNG size: {len(resp.content)} bytes")


class TestClientDocumentDownload:
    """Client document download - P0 fix (asyncio.to_thread)"""

    def test_client_doc_download(self, admin_session):
        """GET client doc download returns 200 with binary content"""
        resp = admin_session.get(
            f"{BASE_URL}/api/trust-cases/{CLIENT_DOC_CASE_ID}/documents/{CLIENT_DOC_ID}/download"
        )
        assert resp.status_code == 200, f"Client doc download failed: {resp.status_code} {resp.text[:300]}"
        assert len(resp.content) > 0, "Response content is empty"
        print(f"Client doc download size: {len(resp.content)} bytes")


class TestAdminDocumentDownload:
    """Admin document download - P0 fix (asyncio.to_thread)"""

    def test_admin_doc_download(self, admin_session):
        """GET admin doc download returns 200"""
        resp = admin_session.get(
            f"{BASE_URL}/api/trust-cases/{ADMIN_DOC_CASE_ID}/admin-documents/{ADMIN_DOC_ID}/download"
        )
        assert resp.status_code == 200, f"Admin doc download failed: {resp.status_code} {resp.text[:300]}"
        assert len(resp.content) > 0, "Response content is empty"
        print(f"Admin doc download size: {len(resp.content)} bytes")
