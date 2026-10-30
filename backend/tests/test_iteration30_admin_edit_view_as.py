# Iteration 30: admin field override (PATCH /fields), View-as-Client read-only mirror, client WhatsApp disabled
import os
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("support@igcfirm.com", "Wllorenzo03!")
CLIENT = ("pwtest_1793318071@igchq-test.com", "NewPass12345")
CASE_ID = "562399a8-0b93-4e0d-9e8b-b6fd829af9ef"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
S = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def client():
    return _login(*CLIENT)


def _case():
    return mdb.trust_cases.find_one({"id": CASE_ID}, {"_id": 0})


# --- Admin field override ---
def test_snapshot_before():
    c = _case()
    assert c
    S["before"] = c
    S["docs"] = mdb.documents.count_documents({"case_id": CASE_ID}) if "documents" in mdb.list_collection_names() else None
    S["case_docs"] = len(c.get("documents") or [])
    print("intake_path", c.get("intake_path"), "trust_type", c.get("trust_type"), "trust_name", c.get("trust_name"),
          "grantors", len(c.get("grantors") or []), "assets", len(c.get("assets") or []), "docs", S["docs"], S["case_docs"])


def test_edit_fields_append_and_rename(admin):
    c = S["before"]
    gr = [{"id": g["id"], "full_legal_name": g["full_legal_name"]} for g in c.get("grantors") or []]
    gr.append({"full_legal_name": "TEST_Admin Grantor"})
    ben = [{"id": b["id"], "full_legal_name": b["full_legal_name"]} for b in c.get("beneficiaries") or []]
    ben.append({"full_legal_name": "TEST_Admin Beneficiary"})
    assets = [{"id": a["id"], "asset_type": a.get("asset_type", "bank"), "institution_name": a.get("institution_name", ""),
               "estimated_value": a.get("estimated_value")} for a in c.get("assets") or []]
    assets.append({"asset_type": "bank", "institution_name": "TEST_Admin Bank", "estimated_value": 1234})
    body = {"intake_path": "new", "trust_name": "TEST_Admin Renamed Trust", "grantors": gr,
            "trustees": [{"full_legal_name": "TEST_Admin Trustee"}],
            "successor_trustees": [{"full_legal_name": "TEST_Admin Successor"}],
            "beneficiaries": ben, "assets": assets}
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["changes"] >= 5
    after = _case()
    assert after["trust_name"] == "TEST_Admin Renamed Trust"
    assert after["intake_path"] == "new"
    assert len(after["grantors"]) == len(c.get("grantors") or []) + 1
    ng = after["grantors"][-1]
    assert ng["full_legal_name"] == "TEST_Admin Grantor" and ng["added_by_admin"] and ng["date_of_birth"] == "" and ng["id"]
    assert len(after["trustees"]) == len(c.get("trustees") or []) + 1
    assert len(after["assets"]) == len(c.get("assets") or []) + 1
    assert after["assets"][-1]["estimated_value"] == 1234
    assert after["admin_edits"][-1]["admin_email"] == ADMIN[0]
    assert len(after.get("documents") or []) == S["case_docs"]
    if S["docs"] is not None:
        assert mdb.documents.count_documents({"case_id": CASE_ID}) == S["docs"]


def test_edit_omitted_entries_not_removed(admin):
    # send only one grantor -> others must not be removed
    c = _case()
    n = len(c["grantors"])
    g0 = c["grantors"][0]
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields",
                    json={"grantors": [{"id": g0["id"], "full_legal_name": g0["full_legal_name"]}]})
    assert r.status_code == 200 and r.json()["changes"] == 0
    assert len(_case()["grantors"]) == n


def test_path_toggle_keeps_lists(admin):
    c = _case()
    n = {k: len(c.get(k) or []) for k in ("grantors", "trustees", "successor_trustees", "beneficiaries", "assets")}
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json={"intake_path": "review"})
    assert r.status_code == 200 and r.json()["changes"] == 1
    assert _case()["intake_path"] == "review"
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json={"intake_path": "new"})
    assert r.status_code == 200
    c2 = _case()
    assert c2["intake_path"] == "new"
    for k, v in n.items():
        assert len(c2.get(k) or []) == v, k


def test_edit_validation(admin):
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json={"intake_path": "bogus"})
    assert r.status_code == 422
    r = admin.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json={"grantors": [{"full_legal_name": ""}]})
    assert r.status_code == 422
    r = admin.patch(f"{API}/admin/trust-cases/nonexistent-id/fields", json={"trust_name": "x"})
    assert r.status_code == 404


def test_edit_requires_admin(client):
    r = client.patch(f"{API}/admin/trust-cases/{CASE_ID}/fields", json={"trust_name": "hack"})
    assert r.status_code == 403


def test_client_sees_admin_added(client):
    r = client.get(f"{API}/trust-cases/{CASE_ID}")
    assert r.status_code == 200, r.text
    names = [g["full_legal_name"] for g in r.json().get("grantors", [])]
    assert "TEST_Admin Grantor" in names


# --- View as client ---
def test_view_as_flow(admin):
    s = _login(*ADMIN)
    r = s.post(f"{API}/admin/trust-cases/{CASE_ID}/view-as-client")
    assert r.status_code == 200, r.text
    assert r.json()["client_name"]
    me = s.get(f"{API}/auth/me").json()
    u = me.get("user", me)
    assert u["email"] == CLIENT[0], me
    assert u.get("view_as_admin") == ADMIN[0]
    assert u.get("view_as_case_id") == CASE_ID
    r = s.get(f"{API}/trust-cases/{CASE_ID}")
    assert r.status_code == 200
    # writes blocked
    r = s.post(f"{API}/trust-cases/{CASE_ID}/grantors", json={"full_legal_name": "TEST_should_not_save"})
    assert r.status_code == 403 and "Read-only" in r.text, r.text
    r = s.post(f"{API}/auth/change-password", json={"current_password": "a", "new_password": "bbbbbbbbbb"})
    assert r.status_code == 403 and "Read-only" in r.text
    # admin APIs blocked while in view-as
    r = s.get(f"{API}/admin/trust-cases")
    assert r.status_code == 403
    # exit
    r = s.post(f"{API}/auth/view-as/exit")
    assert r.status_code == 200
    me = s.get(f"{API}/auth/me").json()
    u = me.get("user", me)
    assert u["email"] == ADMIN[0] and not u.get("view_as_admin")


def test_view_as_requires_admin(client):
    r = client.post(f"{API}/admin/trust-cases/{CASE_ID}/view-as-client")
    assert r.status_code == 403


def test_client_session_unaffected(client):
    me = client.get(f"{API}/auth/me").json()
    u = me.get("user", me)
    assert u["email"] == CLIENT[0] and not u.get("view_as_admin")


# --- Client WhatsApp disabled ---
def test_send_whatsapp_disabled(admin):
    r = admin.post(f"{API}/admin/trust-cases/{CASE_ID}/send-whatsapp", json={"to": "+15555550123", "body": "hello"})
    assert r.status_code == 400, r.text
    assert "Client WhatsApp messaging is turned off" in r.json()["detail"]


def test_password_alert_email_only(admin):
    r = admin.post(f"{API}/admin/users/temp-password", json={"email": CLIENT[0]})
    assert r.status_code == 200, r.text
    temp = r.json()["temp_password"]
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": CLIENT[0], "password": temp}).status_code == 200
    r = s.post(f"{API}/auth/change-password", json={"current_password": temp, "new_password": CLIENT[1]})
    assert r.status_code == 200, r.text
    uid = mdb.users.find_one({"email": CLIENT[0]})["id"]
    t0 = time.time()
    ev = None
    while time.time() - t0 < 40:
        ev = mdb.password_events.find_one({"user_id": uid, "kind": "client_changed"}, {"_id": 0}, sort=[("created_at", -1)])
        if ev and ev.get("alert", {}).get("channel") not in (None, "pending"):
            break
        time.sleep(1)
    print("alert", ev.get("alert"))
    assert ev["alert"]["whatsapp_attempted"] is False
    assert ev["alert"]["channel"] == "email"
