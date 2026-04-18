"""Backend regression tests for Trust Intake & Client Portal."""
import io
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://trust-intake-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"


# ---------- FIXTURES ----------
@pytest.fixture(scope="session")
def client_session():
    s = requests.Session()
    email = f"testclient_{uuid.uuid4().hex[:8]}@example.com"
    password = "ClientPass123"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Test Client"})
    assert r.status_code == 200, r.text
    s.email = email
    s.password = password
    return s


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    assert r.json()["role"] == "admin"
    return s


@pytest.fixture(scope="session")
def case_id(client_session):
    r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- HEALTH ----------
def test_health():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- AUTH ----------
class TestAuth:
    def test_admin_login_role(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        # cookies set
        assert "access_token" in s.cookies or any(c.name == "access_token" for c in s.cookies)

    def test_me_with_cookie(self, admin_session):
        r = admin_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_register_client(self):
        s = requests.Session()
        email = f"testclient_{uuid.uuid4().hex[:6]}@example.com"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Pass1234", "name": "Foo"})
        assert r.status_code == 200
        assert r.json()["role"] == "client"
        # duplicate
        r2 = s.post(f"{API}/auth/register", json={"email": email, "password": "Pass1234", "name": "Foo"})
        assert r2.status_code == 400

    def test_logout_clears(self, admin_session):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        r = s.post(f"{API}/auth/logout")
        assert r.status_code == 200
        r2 = s.get(f"{API}/auth/me")
        assert r2.status_code == 401

    def test_brute_force_lockout(self):
        # use a unique fake email so we don't lock out the real admin for this IP pair
        bad_email = f"nosuchuser_{uuid.uuid4().hex[:6]}@example.com"
        s = requests.Session()
        codes = []
        for _ in range(6):
            r = s.post(f"{API}/auth/login", json={"email": bad_email, "password": "wrong"})
            codes.append(r.status_code)
        # first 5 should be 401, then 429
        assert 429 in codes, f"Expected lockout (429) after 5 bad attempts, got {codes}"


# ---------- TRUST CASES ----------
class TestTrustCases:
    def test_create_single_case(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert r.status_code == 200
        data = r.json()
        assert data["trust_type"] == "single"
        assert data["status"] == "Intake Started"
        assert "id" in data

    def test_create_joint_case(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "joint"})
        assert r.status_code == 200
        assert r.json()["trust_type"] == "joint"

    def test_mine(self, client_session):
        r = client_session.get(f"{API}/trust-cases/mine")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_get_case_403_for_others(self, case_id):
        # a second client should get 403
        s = requests.Session()
        email = f"other_{uuid.uuid4().hex[:6]}@example.com"
        s.post(f"{API}/auth/register", json={"email": email, "password": "Pass1234", "name": "Other"})
        r = s.get(f"{API}/trust-cases/{case_id}")
        assert r.status_code == 403


# ---------- INTAKE SECTIONS ----------
GRANTOR_PAYLOAD = {
    "full_legal_name": "Jane Doe",
    "date_of_birth": "1980-01-01",
    "ssn": "111-22-3333",
    "phone": "555-111-2222",
    "email": "jane@example.com",
    "address": {"line1": "1 Main", "city": "NYC", "state": "NY", "zip": "10001"},
    "marital_status": "Single",
    "citizenship": "US",
}


class TestIntake:
    def test_add_grantor_and_max(self, client_session, case_id):
        r = client_session.post(f"{API}/trust-cases/{case_id}/grantors", json=GRANTOR_PAYLOAD)
        assert r.status_code == 200, r.text
        # single trust => max 1
        r2 = client_session.post(f"{API}/trust-cases/{case_id}/grantors", json=GRANTOR_PAYLOAD)
        assert r2.status_code == 400

    def test_update_and_delete_grantor(self, client_session):
        # new case
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        add = client_session.post(f"{API}/trust-cases/{cid}/grantors", json=GRANTOR_PAYLOAD)
        gid = add.json()["id"]
        upd = client_session.put(f"{API}/trust-cases/{cid}/grantors/{gid}",
                                 json={**GRANTOR_PAYLOAD, "full_legal_name": "Jane Updated"})
        assert upd.status_code == 200
        assert upd.json()["full_legal_name"] == "Jane Updated"
        d = client_session.delete(f"{API}/trust-cases/{cid}/grantors/{gid}")
        assert d.status_code == 200

    def test_set_trustee(self, client_session, case_id):
        payload = {"full_legal_name": "Trustee Name", "relationship": "Spouse",
                   "phone": "555-1", "email": "t@example.com"}
        r = client_session.put(f"{API}/trust-cases/{case_id}/trustee", json=payload)
        assert r.status_code == 200

    def test_successor_trustees_max_3(self, client_session, case_id):
        payload = {"full_legal_name": "Succ", "relationship": "Friend",
                   "phone": "555", "email": "s@example.com"}
        for i in range(3):
            r = client_session.post(f"{API}/trust-cases/{case_id}/successor-trustees", json=payload)
            assert r.status_code == 200, f"Successor {i} failed: {r.text}"
        r = client_session.post(f"{API}/trust-cases/{case_id}/successor-trustees", json=payload)
        assert r.status_code == 400

    def test_add_beneficiary(self, client_session, case_id):
        payload = {"full_legal_name": "Ben Name", "date_of_birth": "2000-01-01",
                   "relationship": "Child", "percentage": 100.0}
        r = client_session.post(f"{API}/trust-cases/{case_id}/beneficiaries", json=payload)
        assert r.status_code == 200
        assert r.json()["full_legal_name"] == "Ben Name"

    def test_asset_real_estate_requires_property_address(self, client_session, case_id):
        bad = {"asset_type": "real_estate"}
        r = client_session.post(f"{API}/trust-cases/{case_id}/assets", json=bad)
        assert r.status_code == 400
        good = {"asset_type": "real_estate", "property_address": "123 St"}
        r2 = client_session.post(f"{API}/trust-cases/{case_id}/assets", json=good)
        assert r2.status_code == 200

    def test_asset_bank_requires_institution(self, client_session, case_id):
        bad = {"asset_type": "bank"}
        r = client_session.post(f"{API}/trust-cases/{case_id}/assets", json=bad)
        assert r.status_code == 400
        good = {"asset_type": "bank", "institution_name": "Bank of X"}
        r2 = client_session.post(f"{API}/trust-cases/{case_id}/assets", json=good)
        assert r2.status_code == 200

    def test_ein_requires_authorized(self, client_session, case_id):
        r = client_session.put(f"{API}/trust-cases/{case_id}/ein",
                               json={"ssn": "111-22-3333", "authorized": False})
        assert r.status_code == 400
        r2 = client_session.put(f"{API}/trust-cases/{case_id}/ein",
                                json={"ssn": "111-22-3333", "authorized": True})
        assert r2.status_code == 200


# ---------- DOCUMENTS ----------
class TestDocuments:
    def test_upload_and_download(self, client_session, case_id):
        files = {"file": ("id.txt", io.BytesIO(b"fakeID"), "text/plain")}
        data = {"doc_type": "government_id"}
        # Session sends cookies; requests' files form needs no content-type on session
        r = client_session.post(f"{API}/trust-cases/{case_id}/documents",
                                data=data, files=files)
        if r.status_code == 503:
            pytest.skip(f"Storage unavailable: {r.text}")
        assert r.status_code == 200, r.text
        doc_id = r.json()["id"]
        dl = client_session.get(f"{API}/trust-cases/{case_id}/documents/{doc_id}/download")
        assert dl.status_code == 200
        assert dl.content == b"fakeID"


# ---------- MESSAGES ----------
class TestMessages:
    def test_post_and_list_and_unread(self, client_session, case_id):
        r = client_session.post(f"{API}/trust-cases/{case_id}/messages",
                                json={"body": "Hello from client", "section": "help"})
        assert r.status_code == 200
        lst = client_session.get(f"{API}/trust-cases/{case_id}/messages")
        assert lst.status_code == 200
        assert any(m["body"] == "Hello from client" for m in lst.json())
        u = client_session.get(f"{API}/messages/unread-count")
        assert u.status_code == 200
        assert "unread" in u.json()


# ---------- ADMIN ----------
class TestAdmin:
    def test_admin_list_cases(self, admin_session):
        r = admin_session.get(f"{API}/admin/trust-cases")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_stats(self, admin_session):
        r = admin_session.get(f"{API}/admin/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_cases" in data and "by_status" in data

    def test_admin_update_status_and_notes(self, admin_session, case_id):
        r = admin_session.put(f"{API}/admin/trust-cases/{case_id}/status",
                              json={"status": "In Review"})
        assert r.status_code == 200
        r2 = admin_session.post(f"{API}/admin/trust-cases/{case_id}/notes",
                                json={"note": "TEST_note"})
        assert r2.status_code == 200
        r3 = admin_session.post(f"{API}/admin/trust-cases/{case_id}/ein-request")
        assert r3.status_code == 200

    def test_admin_invalid_status(self, admin_session, case_id):
        r = admin_session.put(f"{API}/admin/trust-cases/{case_id}/status",
                              json={"status": "BogusStatus"})
        assert r.status_code == 400

    def test_non_admin_forbidden(self, client_session):
        r = client_session.get(f"{API}/admin/trust-cases")
        assert r.status_code == 403


# ---------- BRANDING ----------
class TestBranding:
    def test_get_defaults(self):
        r = requests.get(f"{API}/branding")
        assert r.status_code == 200
        data = r.json()
        assert "business_name" in data and "primary_color" in data

    def test_update_branding_admin(self, admin_session):
        r = admin_session.put(f"{API}/branding", json={"business_name": "TEST_Portal"})
        assert r.status_code == 200
        assert r.json()["business_name"] == "TEST_Portal"
        # reset
        admin_session.put(f"{API}/branding", json={"business_name": "IGC Trust Portal"})

    def test_update_branding_client_forbidden(self, client_session):
        r = client_session.put(f"{API}/branding", json={"business_name": "hack"})
        assert r.status_code == 403
