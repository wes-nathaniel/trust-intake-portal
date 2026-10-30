"""Iteration 31 — free step navigation submit guard (_intake_missing_steps) + admin WhatsApp status alerts."""
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
API = f"{BASE}/api"

ADMIN = ("support@igcfirm.com", "Wllorenzo03!")
PW_CLIENT = ("pwtest_1793318071@igchq-test.com", "NewPass12345")
PW_CASE = "562399a8-0b93-4e0d-9e8b-b6fd829af9ef"
TAG = uuid.uuid4().hex[:8]
NEW_CLIENT = (f"TEST_freenav_{TAG}@example.com", "Client12345!")

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def new_client():
    r = requests.post(f"{API}/auth/register", json={"email": NEW_CLIENT[0], "password": NEW_CLIENT[1], "name": "TEST FreeNav"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    return _login(*NEW_CLIENT)


@pytest.fixture(scope="module")
def new_case(new_client, admin):
    r = new_client.post(f"{API}/trust-cases", json={"trust_type": "single", "trust_name": f"TEST_FREENAV_{TAG}", "intake_path": "new"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    yield cid
    admin.delete(f"{API}/admin/trust-cases/{cid}?delete_user=true", timeout=20)


# Guard on existing incomplete pwtest case
def test_pwtest_case_incomplete_submit_blocked():
    s = _login(*PW_CLIENT)
    r = s.put(f"{API}/trust-cases/{PW_CASE}/acknowledgments", json={"intake_submitted_ack": True}, timeout=20)
    print(r.status_code, r.text)
    assert r.status_code == 400
    assert "Please complete these steps before submitting" in r.json()["detail"]


# Guard on fresh empty case lists all steps
def test_empty_case_lists_all_missing(new_client, new_case):
    r = new_client.put(f"{API}/trust-cases/{new_case}/acknowledgments", json={"intake_submitted_ack": True}, timeout=20)
    assert r.status_code == 400
    d = r.json()["detail"]
    for lbl in ["Grantors", "Trustee", "Successor Trustees", "Beneficiaries", "Assets", "EIN Workflow", "Documents"]:
        assert lbl in d, d
    # other acks still allowed while incomplete
    r2 = new_client.put(f"{API}/trust-cases/{new_case}/acknowledgments", json={"disclosure_ack": True}, timeout=20)
    assert r2.status_code == 200, r2.text


# Complete every step, then submit succeeds -> In Review
def test_complete_all_then_submit(new_client, new_case, admin):
    c, cid = new_client, new_case
    addr = {"line1": "1 Main St", "city": "Austin", "state": "TX", "zip": "78701"}
    r = c.post(f"{API}/trust-cases/{cid}/grantors", json={"full_legal_name": "TEST Grantor", "date_of_birth": "1980-01-01",
               "ssn": "123-45-6789", "phone": "5125550100", "email": "tg@example.com", "address": addr,
               "marital_status": "single", "citizenship": "US"}, timeout=20)
    assert r.status_code == 200, r.text
    r = c.put(f"{API}/trust-cases/{cid}/trustee", json={"full_legal_name": "TEST Trustee", "relationship": "self", "phone": "5125550101", "email": "tt@example.com"}, timeout=20)
    assert r.status_code == 200, r.text
    r = c.post(f"{API}/trust-cases/{cid}/successor-trustees", json={"full_legal_name": "TEST Succ", "relationship": "sibling", "phone": "5125550102", "email": "ts@example.com"}, timeout=20)
    assert r.status_code == 200, r.text
    r = c.post(f"{API}/trust-cases/{cid}/beneficiaries", json={"full_legal_name": "TEST Ben", "date_of_birth": "2010-01-01", "relationship": "child", "percentage": 100}, timeout=20)
    assert r.status_code == 200, r.text
    r = c.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"no_assets_ack": True}, timeout=20)
    assert r.status_code == 200, r.text
    r = c.put(f"{API}/trust-cases/{cid}/ein", json={"authorized": True}, timeout=20)
    assert r.status_code == 200, r.text
    # Still missing only Documents
    r = c.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"intake_submitted_ack": True}, timeout=20)
    assert r.status_code == 400 and "Documents" in r.json()["detail"] and "Grantors" not in r.json()["detail"], r.text
    for dt in ("government_id", "proof_of_address"):
        r = c.post(f"{API}/trust-cases/{cid}/documents", data={"doc_type": dt}, files={"file": (f"{dt}.pdf", io.BytesIO(PDF), "application/pdf")}, timeout=30)
        assert r.status_code == 200, r.text
    r = c.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"intake_submitted_ack": True}, timeout=20)
    assert r.status_code == 200, r.text
    g = admin.get(f"{API}/admin/trust-cases/{cid}", timeout=20).json()
    assert g["status"] == "In Review", g["status"]
    assert g["acknowledgments"]["intake_submitted_ack"] is True


# Admin not blocked + status endpoint with WhatsApp alert
def test_admin_not_blocked_and_status_change(admin, new_client):
    r = new_client.post(f"{API}/trust-cases", json={"trust_type": "single", "trust_name": f"TEST_FREENAV_ADM_{TAG}", "intake_path": "new"}, timeout=20)
    cid = r.json()["id"]
    try:
        r = admin.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"intake_submitted_ack": True}, timeout=20)
        assert r.status_code == 200, r.text
        r = admin.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "Waiting on Documents"}, timeout=30)
        assert r.status_code == 200, r.text
        g = admin.get(f"{API}/admin/trust-cases/{cid}", timeout=20).json()
        assert g["status"] == "Waiting on Documents"
    finally:
        admin.delete(f"{API}/admin/trust-cases/{cid}?delete_user=false", timeout=20)
