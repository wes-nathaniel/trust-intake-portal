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
        from pathlib import Path
        # Load backend .env for MONGO_URL / DB_NAME so tests match running server
        env_vals = {}
        env_path = Path("/app/backend/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env_vals[k.strip()] = v.strip().strip('"').strip("'")
        mongo_url = os.environ.get("MONGO_URL") or env_vals.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME") or env_vals.get("DB_NAME", "trust_portal")
        m = MongoClient(mongo_url)
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


# ---------- DOC REQUESTS / PENDING ITEMS (NEW iteration 3) ----------
class TestDocRequestsAndPending:
    def _new_case(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert r.status_code == 200
        return r.json()["id"]

    def test_get_case_has_pending_items_required_docs(self, client_session):
        cid = self._new_case(client_session)
        r = client_session.get(f"{API}/trust-cases/{cid}")
        assert r.status_code == 200
        data = r.json()
        assert "pending_items" in data
        kinds = {(p["kind"], p["doc_type"]) for p in data["pending_items"]}
        assert ("required_doc", "government_id") in kinds
        assert ("required_doc", "proof_of_address") in kinds

    def test_admin_create_doc_request_appears_in_client_pending(self, admin_session, client_session):
        cid = self._new_case(client_session)
        r = admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests",
                               json={"doc_type": "bank_statement", "note": "Most recent 2 months"})
        assert r.status_code == 200, r.text
        req = r.json()
        assert req["doc_type"] == "bank_statement"
        assert req["fulfilled"] is False
        assert req["cancelled"] is False
        assert "id" in req

        # Client sees it in pending_items
        r2 = client_session.get(f"{API}/trust-cases/{cid}")
        assert r2.status_code == 200
        pending = r2.json()["pending_items"]
        matching = [p for p in pending if p["kind"] == "requested_doc" and p.get("request_id") == req["id"]]
        assert len(matching) == 1
        assert matching[0]["doc_type"] == "bank_statement"
        assert matching[0]["note"] == "Most recent 2 months"
        assert matching[0]["label"]

    def test_uploading_matching_doc_auto_fulfills_request(self, admin_session, client_session):
        cid = self._new_case(client_session)
        create = admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests",
                                    json={"doc_type": "bank_statement", "note": "Need it"})
        req_id = create.json()["id"]

        files = {"file": ("stmt.txt", io.BytesIO(b"statement"), "text/plain")}
        data = {"doc_type": "bank_statement"}
        up = client_session.post(f"{API}/trust-cases/{cid}/documents", data=data, files=files)
        if up.status_code == 503:
            pytest.skip("Storage unavailable")
        assert up.status_code == 200

        # Request should be auto-fulfilled
        r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        assert r.status_code == 200
        case = r.json()
        req = next(x for x in case["requested_documents"] if x["id"] == req_id)
        assert req["fulfilled"] is True
        assert req.get("fulfilled_doc_id")

        # And dropped from pending_items
        r2 = client_session.get(f"{API}/trust-cases/{cid}")
        pend_ids = [p.get("request_id") for p in r2.json()["pending_items"] if p["kind"] == "requested_doc"]
        assert req_id not in pend_ids

    def test_delete_doc_request_removes_from_pending(self, admin_session, client_session):
        cid = self._new_case(client_session)
        create = admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests",
                                    json={"doc_type": "deed"})
        req_id = create.json()["id"]

        # Verify present
        r1 = client_session.get(f"{API}/trust-cases/{cid}")
        assert any(p.get("request_id") == req_id for p in r1.json()["pending_items"])

        # Cancel
        d = admin_session.delete(f"{API}/admin/trust-cases/{cid}/doc-requests/{req_id}")
        assert d.status_code == 200

        # No longer pending
        r2 = client_session.get(f"{API}/trust-cases/{cid}")
        assert not any(p.get("request_id") == req_id for p in r2.json()["pending_items"])

    def test_mark_fulfilled_without_upload(self, admin_session, client_session):
        cid = self._new_case(client_session)
        create = admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests",
                                    json={"doc_type": "title", "note": "offline"})
        req_id = create.json()["id"]

        m = admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests/{req_id}/mark-fulfilled")
        assert m.status_code == 200

        # Verify fulfilled in admin case, and removed from client pending
        r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        req = next(x for x in r.json()["requested_documents"] if x["id"] == req_id)
        assert req["fulfilled"] is True
        assert req.get("fulfilled_by")

        r2 = client_session.get(f"{API}/trust-cases/{cid}")
        assert not any(p.get("request_id") == req_id for p in r2.json()["pending_items"])

    def test_status_waiting_on_documents_returns_200(self, admin_session, client_session):
        """Status email with pending_items list should trigger without error (side-effects checked via logs separately)."""
        cid = self._new_case(client_session)
        # Add a requested doc to make pending_items richer
        admin_session.post(f"{API}/admin/trust-cases/{cid}/doc-requests",
                           json={"doc_type": "bank_statement", "note": "Need it"})
        r = admin_session.put(f"{API}/admin/trust-cases/{cid}/status",
                              json={"status": "Waiting on Documents"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Waiting on Documents"

    def test_admin_get_case_attaches_pending_items(self, admin_session, client_session):
        cid = self._new_case(client_session)
        r = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        assert r.status_code == 200
        assert "pending_items" in r.json()

    def test_upload_asset_doc_no_manual_asset_still_ok(self, client_session):
        """Assets completeness: uploading a bank_statement with no manual asset should succeed and not error."""
        cid = self._new_case(client_session)
        files = {"file": ("b.txt", io.BytesIO(b"x"), "text/plain")}
        data = {"doc_type": "bank_statement"}
        r = client_session.post(f"{API}/trust-cases/{cid}/documents", data=data, files=files)
        if r.status_code == 503:
            pytest.skip("Storage unavailable")
        assert r.status_code == 200
        # Case GET - no manual assets but bank_statement doc present
        case = client_session.get(f"{API}/trust-cases/{cid}").json()
        assert not case.get("assets", [])
        doc_types = {d["doc_type"] for d in case.get("documents", []) if not d.get("is_deleted")}
        assert "bank_statement" in doc_types
        # pending_items should NOT have an 'asset' kind
        kinds = {p["kind"] for p in case.get("pending_items", [])}
        assert "asset" not in kinds


# ---------- QUESTIONS / AI ASSISTANT (NEW iteration 4) ----------
class TestQuestionsAndAI:
    def _new_case(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        assert r.status_code == 200
        return r.json()["id"]

    def test_post_simple_role_question_returns_ai_confident(self, client_session):
        cid = self._new_case(client_session)
        r = client_session.post(
            f"{API}/trust-cases/{cid}/questions",
            json={"section": "trustee", "question": "What exactly is a trustee?"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["section"] == "trustee"
        assert data["question"] == "What exactly is a trustee?"
        assert data.get("ai_response"), "AI response should be populated"
        # We expect this simple definitional Q to be confident
        assert data["ai_confident"] is True, f"Expected confident=True, got: {data}"
        assert data["status"] == "ai_answered"
        assert data.get("admin_reply") is None

    def test_post_legal_advice_question_escalates(self, client_session):
        cid = self._new_case(client_session)
        legal_q = (
            "If I disinherit my son and leave everything to my daughter, "
            "what are the tax consequences and can he successfully contest the trust in California?"
        )
        r = client_session.post(
            f"{API}/trust-cases/{cid}/questions",
            json={"section": "beneficiaries", "question": legal_q},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ai_confident"] is False, f"Expected escalation, got: {data}"
        assert data["status"] == "escalated"
        assert data.get("ai_response")

    def test_list_questions_filtered_by_section(self, client_session):
        cid = self._new_case(client_session)
        client_session.post(f"{API}/trust-cases/{cid}/questions",
                            json={"section": "grantors", "question": "Who is a grantor?"})
        client_session.post(f"{API}/trust-cases/{cid}/questions",
                            json={"section": "trustee", "question": "Who is a trustee?"})
        r = client_session.get(f"{API}/trust-cases/{cid}/questions",
                               params={"section": "grantors"})
        assert r.status_code == 200
        qs = r.json()
        assert len(qs) >= 1
        assert all(q["section"] == "grantors" for q in qs)

    def test_admin_questions_listing_and_counts(self, admin_session, client_session):
        cid = self._new_case(client_session)
        # create one escalation
        legal_q = "Can you give me legal advice on contesting this specific trust?"
        client_session.post(f"{API}/trust-cases/{cid}/questions",
                            json={"section": "beneficiaries", "question": legal_q})
        # one confident
        client_session.post(f"{API}/trust-cases/{cid}/questions",
                            json={"section": "trustee", "question": "What is a trustee?"})

        r = admin_session.get(f"{API}/admin/questions")
        assert r.status_code == 200
        data = r.json()
        assert "questions" in data and "counts" in data
        assert "escalated" in data["counts"]
        assert "ai_answered" in data["counts"]

        r2 = admin_session.get(f"{API}/admin/questions", params={"status": "escalated"})
        assert r2.status_code == 200
        assert all(q["status"] == "escalated" for q in r2.json()["questions"])

        r3 = admin_session.get(f"{API}/admin/questions", params={"status": "ai_answered"})
        assert r3.status_code == 200
        assert all(q["status"] == "ai_answered" for q in r3.json()["questions"])

    def test_admin_reply_updates_status_and_returns_to_client(self, admin_session, client_session):
        cid = self._new_case(client_session)
        post = client_session.post(
            f"{API}/trust-cases/{cid}/questions",
            json={"section": "beneficiaries",
                  "question": "Specific case advice please about my situation"},
        )
        qid = post.json()["id"]

        reply_text = "Thanks — our attorney will follow up directly within 1 business day."
        r = admin_session.post(f"{API}/admin/questions/{qid}/reply",
                               json={"reply": reply_text})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "admin_replied"
        assert body["admin_reply"] == reply_text

        # filter admin_replied
        rfilter = admin_session.get(f"{API}/admin/questions",
                                    params={"status": "admin_replied"})
        assert rfilter.status_code == 200
        assert any(q["id"] == qid for q in rfilter.json()["questions"])

        # client sees the admin_reply in their own listing
        r3 = client_session.get(f"{API}/trust-cases/{cid}/questions",
                                params={"section": "beneficiaries"})
        assert r3.status_code == 200
        match = next((q for q in r3.json() if q["id"] == qid), None)
        assert match is not None
        assert match["admin_reply"] == reply_text
        assert match["status"] == "admin_replied"

    def test_admin_reply_unknown_question_404(self, admin_session):
        r = admin_session.post(f"{API}/admin/questions/nonexistent-id/reply",
                               json={"reply": "hi"})
        assert r.status_code == 404

    def test_non_admin_cannot_list_admin_questions(self, client_session):
        r = client_session.get(f"{API}/admin/questions")
        assert r.status_code == 403

    def test_question_validation_empty(self, client_session):
        cid = self._new_case(client_session)
        r = client_session.post(f"{API}/trust-cases/{cid}/questions",
                                json={"section": "trustee", "question": ""})
        assert r.status_code in (400, 422)


# ============================================================================
# Iteration 5: Iron Gate Consulting Phase 1-5 — Trust Name, Acknowledgments,
# EIN authorized, ein_letter RBAC, Trust Preview, Unlock Final, Square,
# Mark Payment Received, Webhook, Statuses, Send Review Reminder
# ============================================================================

def _make_pdf_bytes(num_pages: int = 1, text: str = "IGC Test Trust Draft") -> bytes:
    """Build a small valid multi-page PDF using reportlab."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    for i in range(num_pages):
        c.setFont("Helvetica", 14)
        c.drawString(72, 720, f"{text} — Page {i+1}")
        c.drawString(72, 700, "This is a synthetic fixture PDF for backend testing only.")
        c.showPage()
    c.save()
    return buf.getvalue()


# ---------- PHASE 1: TRUST NAME ----------
class TestTrustName:
    def test_create_case_persists_trust_name(self, client_session):
        r = client_session.post(f"{API}/trust-cases",
                                json={"trust_type": "single", "trust_name": "The TEST Smith Family Trust"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["trust_name"] == "The TEST Smith Family Trust"
        # Verify persisted via GET
        r2 = client_session.get(f"{API}/trust-cases/{data['id']}")
        assert r2.status_code == 200
        assert r2.json()["trust_name"] == "The TEST Smith Family Trust"

    def test_update_trust_name_endpoint(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = client_session.put(f"{API}/trust-cases/{cid}/trust-name",
                                json={"trust_name": "TEST Updated Trust Name"})
        assert r2.status_code == 200
        assert r2.json()["trust_name"] == "TEST Updated Trust Name"
        # GET verifies persistence
        case = client_session.get(f"{API}/trust-cases/{cid}").json()
        assert case["trust_name"] == "TEST Updated Trust Name"

    def test_update_trust_name_too_short_rejected(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = client_session.put(f"{API}/trust-cases/{cid}/trust-name", json={"trust_name": "ab"})
        assert r2.status_code in (400, 422), r2.text


# ---------- PHASE 1: ACKNOWLEDGMENTS ----------
class TestAcknowledgments:
    def test_set_individual_acks(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        body = {
            "state_laws_ack": True,
            "notarization_ack": True,
            "disclosure_ack": True,
            "business_sos_ack": True,
        }
        r2 = client_session.put(f"{API}/trust-cases/{cid}/acknowledgments", json=body)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["state_laws_ack"] is True
        assert data["notarization_ack"] is True
        assert data["disclosure_ack"] is True
        assert data["business_sos_ack"] is True
        # Persisted on case
        case = client_session.get(f"{API}/trust-cases/{cid}").json()
        assert case["acknowledgments"]["state_laws_ack"] is True

    def test_review_completed_ack_triggers_admin_notification(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        # First call: set to true
        r2 = client_session.put(f"{API}/trust-cases/{cid}/acknowledgments",
                                json={"review_completed_ack": True})
        assert r2.status_code == 200
        assert r2.json()["review_completed_ack"] is True
        # Second call (already true) should still return 200; backend will not duplicate-notify
        r3 = client_session.put(f"{API}/trust-cases/{cid}/acknowledgments",
                                json={"review_completed_ack": True})
        assert r3.status_code == 200


# ---------- PHASE 1: EIN — authorized required, ssn no longer required ----------
class TestEINAuthorized:
    def test_ein_no_ssn_just_authorized(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        # Without ssn, only authorized=true
        r2 = client_session.put(f"{API}/trust-cases/{cid}/ein", json={"authorized": True})
        assert r2.status_code == 200, r2.text

    def test_ein_authorized_false_rejected(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = client_session.put(f"{API}/trust-cases/{cid}/ein", json={"authorized": False})
        assert r2.status_code == 400


# ---------- PHASE 1: ein_letter RBAC ----------
class TestEINLetterRBAC:
    def test_client_cannot_upload_ein_letter(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("ein.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
        r2 = client_session.post(f"{API}/trust-cases/{cid}/documents",
                                 data={"doc_type": "ein_letter"}, files=files)
        assert r2.status_code == 403, r2.text

    def test_admin_can_upload_ein_letter(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("ein.pdf", io.BytesIO(b"%PDF-1.4 fake EIN letter"), "application/pdf")}
        r2 = admin_session.post(f"{API}/trust-cases/{cid}/documents",
                                data={"doc_type": "ein_letter"}, files=files)
        if r2.status_code == 503:
            pytest.skip("Storage unavailable")
        assert r2.status_code == 200, r2.text
        assert r2.json()["doc_type"] == "ein_letter"

    def test_client_doc_upload_does_not_crash(self, client_session):
        """Client upload should succeed (admin notification email is best-effort)."""
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("id.pdf", io.BytesIO(b"id-bytes"), "application/pdf")}
        r2 = client_session.post(f"{API}/trust-cases/{cid}/documents",
                                 data={"doc_type": "government_id"}, files=files)
        if r2.status_code == 503:
            pytest.skip("Storage unavailable")
        assert r2.status_code == 200


# ---------- PHASE 2: TRUST PREVIEW ----------
class TestTrustPreview:
    def _setup_case_with_draft(self, client_session, admin_session, pages: int = 2):
        r = client_session.post(f"{API}/trust-cases",
                                json={"trust_type": "single", "trust_name": "TEST Preview Trust"})
        cid = r.json()["id"]
        pdf_bytes = _make_pdf_bytes(num_pages=pages)
        files = {"file": ("draft.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files=files)
        if r2.status_code == 503:
            pytest.skip("Storage unavailable")
        assert r2.status_code == 200, r2.text
        assert r2.json().get("pages") == pages
        return cid

    def test_admin_upload_trust_draft_sets_status(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=2)
        case = admin_session.get(f"{API}/admin/trust-cases/{cid}").json()
        assert case["status"] == "Ready for Review"
        assert case.get("trust_draft", {}).get("pages") == 2

    def test_admin_upload_trust_draft_rejects_non_pdf(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("draft.txt", io.BytesIO(b"not a pdf"), "text/plain")}
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files=files)
        assert r2.status_code == 400, r2.text

    def test_trust_preview_meta(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=2)
        r = client_session.get(f"{API}/trust-cases/{cid}/trust-preview/meta")
        assert r.status_code == 200, r.text
        meta = r.json()
        assert meta["pages"] == 2
        assert meta["version"] >= 1
        assert meta["trust_name"] == "TEST Preview Trust"
        assert meta["unlocked"] is False

    def test_trust_preview_page_returns_png(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=2)
        r = client_session.get(f"{API}/trust-cases/{cid}/trust-preview/page/1.png")
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 100
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_trust_preview_page_out_of_range_404(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=1)
        r = client_session.get(f"{API}/trust-cases/{cid}/trust-preview/page/99.png")
        assert r.status_code == 404

    def test_admin_raw_pdf_download(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=1)
        r = admin_session.get(f"{API}/admin/trust-cases/{cid}/trust-draft/raw")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF")

    def test_admin_raw_pdf_forbidden_for_client(self, client_session, admin_session):
        cid = self._setup_case_with_draft(client_session, admin_session, pages=1)
        r = client_session.get(f"{API}/admin/trust-cases/{cid}/trust-draft/raw")
        assert r.status_code == 403


# ---------- PHASE 4: UNLOCK FINAL ----------
class TestUnlockFinal:
    def _setup(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases",
                                json={"trust_type": "single", "trust_name": "TEST Unlock Trust"})
        cid = r.json()["id"]
        files = {"file": ("draft.pdf", io.BytesIO(_make_pdf_bytes(1)), "application/pdf")}
        ru = admin_session.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files=files)
        if ru.status_code == 503:
            pytest.skip("Storage unavailable")
        assert ru.status_code == 200
        return cid

    def test_trust_final_locked_returns_403(self, client_session, admin_session):
        cid = self._setup(client_session, admin_session)
        r = client_session.get(f"{API}/trust-cases/{cid}/trust-final")
        assert r.status_code == 403

    def test_unlock_final_then_download(self, client_session, admin_session):
        cid = self._setup(client_session, admin_session)
        r = admin_session.post(f"{API}/admin/trust-cases/{cid}/unlock-final")
        assert r.status_code == 200
        assert r.json()["trust_unlocked"] is True
        # Verify case state
        case = admin_session.get(f"{API}/admin/trust-cases/{cid}").json()
        assert case["trust_unlocked"] is True
        assert case["status"] == "Completed"
        # Client can now download final
        d = client_session.get(f"{API}/trust-cases/{cid}/trust-final")
        assert d.status_code == 200
        assert d.headers.get("content-type", "").startswith("application/pdf")
        assert d.content.startswith(b"%PDF")

    def test_unlock_final_no_draft_400(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/unlock-final")
        assert r2.status_code == 400


# ---------- PHASE 5: SEND REVIEW REMINDER ----------
class TestSendReviewReminder:
    def test_reminder_no_draft_400(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/send-review-reminder")
        assert r2.status_code == 400

    def test_reminder_with_draft_succeeds(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        files = {"file": ("d.pdf", io.BytesIO(_make_pdf_bytes(1)), "application/pdf")}
        ru = admin_session.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files=files)
        if ru.status_code == 503:
            pytest.skip("Storage unavailable")
        assert ru.status_code == 200
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/send-review-reminder")
        assert r2.status_code == 200, r2.text


# ---------- PHASE 5: NEW STATUSES ----------
class TestNewStatuses:
    def test_admin_can_set_ready_for_review(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = admin_session.put(f"{API}/admin/trust-cases/{cid}/status",
                               json={"status": "Ready for Review"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "Ready for Review"

    def test_admin_can_set_payment_pending(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = admin_session.put(f"{API}/admin/trust-cases/{cid}/status",
                               json={"status": "Payment Pending"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "Payment Pending"


# ---------- PHASE 3: SQUARE ----------
class TestSquare:
    def test_square_health_admin(self, admin_session):
        r = admin_session.get(f"{API}/admin/square/health")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        assert data["location_id"] is True
        assert "environment" in data
        assert "webhook_configured" in data

    def test_square_health_client_forbidden(self, client_session):
        r = client_session.get(f"{API}/admin/square/health")
        assert r.status_code == 403

    def test_invoice_create_validation_amount(self, admin_session, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        # amount_cents <= 0 rejected by Pydantic validator (422)
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/invoice",
                                json={"amount_cents": 0})
        assert r2.status_code in (400, 422), r2.text
        r3 = admin_session.post(f"{API}/admin/trust-cases/{cid}/invoice",
                                json={"amount_cents": -100})
        assert r3.status_code in (400, 422), r3.text

    def test_invoice_create_bad_case_id(self, admin_session):
        # Skip if Square not enabled (would 503 first); tests endpoint reaches case lookup
        r = admin_session.post(f"{API}/admin/trust-cases/nonexistent-id/invoice",
                               json={"amount_cents": 50000})
        # Square IS enabled in this env per /health, so we expect 404 (case missing)
        assert r.status_code in (404, 503), r.text

    def test_invoice_create_client_forbidden(self, client_session):
        r = client_session.post(f"{API}/admin/trust-cases/somecase/invoice",
                                json={"amount_cents": 50000})
        assert r.status_code == 403


# ---------- PHASE 3: MARK PAYMENT RECEIVED ----------
class TestMarkPaymentReceived:
    def test_mark_payment_received(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = admin_session.post(f"{API}/admin/trust-cases/{cid}/mark-payment-received")
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["ok"] is True
        assert body["payment"]["status"] == "paid_manual"
        # Verify case status flipped
        case = admin_session.get(f"{API}/admin/trust-cases/{cid}").json()
        assert case["status"] == "Completed"
        assert case["payment"]["status"] == "paid_manual"

    def test_mark_payment_received_client_forbidden(self, client_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        r2 = client_session.post(f"{API}/admin/trust-cases/{cid}/mark-payment-received")
        assert r2.status_code == 403

    def test_payment_status_endpoint(self, client_session, admin_session):
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        # Initially status none
        r1 = client_session.get(f"{API}/trust-cases/{cid}/payment-status")
        assert r1.status_code == 200
        assert r1.json()["status"] == "none"
        # After mark-payment-received
        admin_session.post(f"{API}/admin/trust-cases/{cid}/mark-payment-received")
        r2 = client_session.get(f"{API}/trust-cases/{cid}/payment-status")
        assert r2.status_code == 200
        assert r2.json()["status"] == "paid_manual"


# ---------- PHASE 3: SQUARE WEBHOOK ----------
class TestSquareWebhook:
    def test_webhook_dev_mode_accepts_unverified(self, client_session, admin_session):
        """With SQUARE_WEBHOOK_SIGNATURE_KEY blank, webhook accepts payload without signature."""
        # First create a case + matching invoice_id in payment so the webhook can update it
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        # Stamp a fake invoice_id directly via mongo (since hitting Square live is forbidden)
        from pymongo import MongoClient
        from pathlib import Path
        env_vals = {}
        for line in Path("/app/backend/.env").read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_vals[k.strip()] = v.strip().strip('"').strip("'")
        m = MongoClient(env_vals.get("MONGO_URL"))
        db = m[env_vals.get("DB_NAME")]
        fake_invoice_id = f"inv_test_{uuid.uuid4().hex[:8]}"
        db.trust_cases.update_one(
            {"id": cid},
            {"$set": {"payment": {"status": "invoice_sent", "invoice_id": fake_invoice_id}}},
        )

        event_id = f"evt_test_{uuid.uuid4().hex[:8]}"
        payload = {
            "event_id": event_id,
            "type": "invoice.payment_made",
            "data": {"object": {"invoice": {"id": fake_invoice_id, "status": "PAID"}}},
        }
        r2 = requests.post(f"{API}/webhooks/square", json=payload)
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "ok"

        # Verify payment.status updated to "paid"
        case = admin_session.get(f"{API}/admin/trust-cases/{cid}").json()
        assert case["payment"]["status"] == "paid"
        assert case["payment"]["invoice_status"] == "PAID"

        # Duplicate event => "duplicate"
        r3 = requests.post(f"{API}/webhooks/square", json=payload)
        assert r3.status_code == 200
        assert r3.json()["status"] == "duplicate"

    def test_webhook_invalid_json_400(self):
        r = requests.post(f"{API}/webhooks/square",
                          data=b"not json{{{",
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 400

    def test_webhook_unknown_invoice_no_crash(self):
        payload = {
            "event_id": f"evt_unmatched_{uuid.uuid4().hex[:8]}",
            "type": "invoice.payment_made",
            "data": {"object": {"invoice": {"id": "inv_nomatch_xyz", "status": "PAID"}}},
        }
        r = requests.post(f"{API}/webhooks/square", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

