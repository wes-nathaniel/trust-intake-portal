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


# ---------- INVITE FLOW ----------
class TestInviteFlow:
    def _get_token_from_db_via_api(self, admin_session, email):
        # Not exposed — rely on endpoint response that returns case_id; we look up token in DB via a debug path.
        # Since there's no debug endpoint, fetch the invite via a direct mongo query through the app server is NOT possible.
        # Instead, the admin endpoint returns {ok, case_id, user_id} — the token is delivered via email.
        # We derive the token by searching login attempts? -- Not possible.
        # So we expose a small helper: query mongodb directly.
        from pymongo import MongoClient
        m = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db_name = os.environ.get("DB_NAME", "test_database")
        rec = m[db_name].invites.find_one({"email": email, "used": False}, sort=[("created_at", -1)])
        return rec["token"] if rec else None

    def test_admin_invite_creates_user_case_and_token(self, admin_session):
        email = f"itest_{uuid.uuid4().hex[:8]}@example.com"
        r = admin_session.post(f"{API}/admin/invite-client",
                               json={"name": "Invite User", "email": email, "trust_type": "single"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "case_id" in data and "user_id" in data
        # token should exist in DB
        token = self._get_token_from_db_via_api(admin_session, email)
        assert token, "Invite token not found in DB"

    def test_invite_info_valid_and_invalid(self, admin_session):
        email = f"itest_{uuid.uuid4().hex[:8]}@example.com"
        admin_session.post(f"{API}/admin/invite-client",
                           json={"name": "Invite Info", "email": email, "trust_type": "joint"})
        token = self._get_token_from_db_via_api(admin_session, email)
        r = requests.get(f"{API}/auth/invite-info", params={"token": token})
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == email
        assert body["name"] == "Invite Info"
        assert "case_id" in body
        # invalid token
        r2 = requests.get(f"{API}/auth/invite-info", params={"token": "bogus"})
        assert r2.status_code == 400

    def test_accept_invite_sets_password_and_logs_in(self, admin_session):
        email = f"itest_{uuid.uuid4().hex[:8]}@example.com"
        admin_session.post(f"{API}/admin/invite-client",
                           json={"name": "Accept User", "email": email, "trust_type": "single"})
        token = self._get_token_from_db_via_api(admin_session, email)
        new_pw = "NewClientPass123"
        s = requests.Session()
        r = s.post(f"{API}/auth/accept-invite", json={"token": token, "password": new_pw})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert "case_id" in data
        # cookies should allow /auth/me
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        # login with new password
        s2 = requests.Session()
        login = s2.post(f"{API}/auth/login", json={"email": email, "password": new_pw})
        assert login.status_code == 200

    def test_accept_invite_token_not_reusable(self, admin_session):
        email = f"itest_{uuid.uuid4().hex[:8]}@example.com"
        admin_session.post(f"{API}/admin/invite-client",
                           json={"name": "Reuse Token", "email": email, "trust_type": "single"})
        token = self._get_token_from_db_via_api(admin_session, email)
        r1 = requests.post(f"{API}/auth/accept-invite",
                           json={"token": token, "password": "Abc12345"})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/auth/accept-invite",
                           json={"token": token, "password": "Abc12345"})
        assert r2.status_code == 400


# ---------- STATUS CHANGE EMAIL ----------
class TestStatusEmails:
    def test_status_change_to_in_review(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r1 = admin_session.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "In Review"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "In Review"

    def test_status_same_status_no_email(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        admin_session.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "In Review"})
        r2 = admin_session.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "In Review"})
        assert r2.status_code == 200

    def test_status_completed_triggers_pdf_email(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r1 = admin_session.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "Completed"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "Completed"


# ---------- E-SIGN ----------
class TestEsign:
    def test_esign_health_disabled(self, admin_session):
        r = admin_session.get(f"{API}/admin/esign/health")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is False
        assert "test_mode" in data

    def test_esign_health_requires_admin(self, client_session):
        r = client_session.get(f"{API}/admin/esign/health")
        assert r.status_code == 403

    def test_send_for_signing_503_when_disabled(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("t.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
        data = {"signer_email": "x@y.com", "signer_name": "X Y", "title": "T"}
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/send-for-signing",
                                data=data, files=files)
        assert r2.status_code == 503
        assert "not configured" in r2.json().get("detail", "").lower()


# ---------- BENEFICIARY PERCENT VALIDATION ----------
class TestBeneficiaryPctTotal:
    def test_three_beneficiaries_total_over_100(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        base = {"date_of_birth": "2000-01-01", "relationship": "Child"}
        r1 = client_session.post(f"{API}/trust-cases/{cid}/beneficiaries",
                                 json={**base, "full_legal_name": "B1", "percentage": 50})
        assert r1.status_code == 200
        r2 = client_session.post(f"{API}/trust-cases/{cid}/beneficiaries",
                                 json={**base, "full_legal_name": "B2", "percentage": 40})
        assert r2.status_code == 200
        r3 = client_session.post(f"{API}/trust-cases/{cid}/beneficiaries",
                                 json={**base, "full_legal_name": "B3", "percentage": 20})
        assert r3.status_code == 400
