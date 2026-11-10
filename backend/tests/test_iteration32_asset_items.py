# Iteration 32: "Tell us what you own" asset items, Transfer Method Library, Schedule A, intake summary
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
CID = "562399a8-0b93-4e0d-9e8b-b6fd829af9ef"
CLIENT = {"email": "pwtest_1793318071@igchq-test.com", "password": "NewPass12345"}
ADMIN = {"email": "support@igcfirm.com", "password": "Wllorenzo03!"}
STATE = "Texas"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=creds)
    if r.status_code != 200:
        pytest.skip(f"login failed {creds['email']}: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def client():
    return _login(CLIENT)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def created(client):
    ids, method_ids = [], []
    yield {"items": ids, "methods": method_ids}
    for i in ids:
        client.delete(f"{BASE_URL}/trust-cases/{CID}/asset-items/{i}")
    # No DELETE endpoint for library rows: remove TEST rows we created by id directly
    if method_ids and os.environ.get("MONGO_URL"):
        from pymongo import MongoClient
        mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        for mid in method_ids:
            mdb.transfer_methods.delete_one({"id": mid})


@pytest.fixture(scope="module", autouse=True)
def grantor_state(client):
    # Give Grantor 1 an address state so the default can be verified
    case = client.get(f"{BASE_URL}/trust-cases/{CID}").json()
    g = case["grantors"][0]
    if (g.get("address") or {}).get("state") != STATE:
        g["address"] = {**(g.get("address") or {}), "state": STATE}
        if not g.get("email"):
            g["email"] = CLIENT["email"]
        r = client.put(f"{BASE_URL}/trust-cases/{CID}/grantors/{g['id']}", json=g)
        assert r.status_code == 200, r.text
    yield


def _count(s):
    return len(s.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"])


def _add(s, created, **kw):
    body = {"description": f"TEST_{uuid.uuid4().hex[:5]}", "kind": "bank", **kw}
    r = s.post(f"{BASE_URL}/trust-cases/{CID}/asset-items", json=body)
    if r.status_code == 200:
        created["items"].append(r.json()["id"])
    return r


# --- client GET / client_state
def test_client_state_default(client):
    d = client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()
    assert d["client_state"] == STATE


# --- validation
@pytest.mark.parametrize("desc,kind,extra,frag", [
    ("TEST my IRA at Fidelity", "investment", {}, "Retirement"),
    ("TEST account 123456789", "bank", {}, "account numbers"),
    ("TEST some thing", "other", {}, "tell us what it is"),
    ("TEST some thing", "other", {"other_kind": "Something Else"}, "own words"),
    ("TEST thing", "nonsense", {}, "kind"),
])
def test_validation(client, desc, kind, extra, frag):
    r = client.post(f"{BASE_URL}/trust-cases/{CID}/asset-items", json={"description": desc, "kind": kind, **extra})
    assert r.status_code == 400
    assert frag.lower() in r.json()["detail"].lower()


def test_false_positive_457_street(client, created):
    # '457' is in the retirement regex; a street number 457 should NOT be rejected
    r = _add(client, created, description="TEST_House at 457 Oak Street", kind="house_land")
    assert r.status_code == 200, r.text


def test_moved_requires_date_and_method(client):
    r = client.post(f"{BASE_URL}/trust-cases/{CID}/asset-items",
                    json={"description": "TEST_x", "kind": "bank", "not_done": False})
    assert r.status_code == 400
    r = client.post(f"{BASE_URL}/trust-cases/{CID}/asset-items",
                    json={"description": "TEST_x", "kind": "bank", "not_done": False, "date_delivered": "2025-01-02",
                          "method": "__other__"})
    assert r.status_code == 400 and "paper" in r.json()["detail"].lower()


# --- create/planned/moved/edit/delete
def test_crud_flow(client, created):
    r = _add(client, created, description="TEST_House on Elm", kind="house_land", in_trust="yes")
    assert r.status_code == 200
    it = r.json()
    assert it["status"] == "planned" and it["state"] == STATE and it["date_delivered"] == ""
    # moved
    body = {"description": "TEST_House on Elm", "kind": "house_land", "state": STATE, "not_done": False,
            "date_delivered": "2025-03-01", "method": "Deed recorded with the county where the property is located"}
    r = client.put(f"{BASE_URL}/trust-cases/{CID}/asset-items/{it['id']}", json=body)
    assert r.status_code == 200
    got = next(i for i in client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"] if i["id"] == it["id"])
    assert got["status"] == "moved" and got["date_delivered"] == "2025-03-01"
    # unsure method keeps planned
    r = _add(client, created, kind="bank", not_done=False, date_delivered="2025-01-01", method="__unsure__")
    assert r.json()["status"] == "planned" and r.json()["flags"]["unsure"] is True
    # other
    r = _add(client, created, kind="other", other_kind="Something Else", other_text="TEST_Horse saddle")
    assert r.json()["flags"]["other"] is True
    # delete
    rid = created["items"].pop()
    assert client.delete(f"{BASE_URL}/trust-cases/{CID}/asset-items/{rid}").status_code == 200
    assert rid not in [i["id"] for i in client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"]]


def test_transfer_methods_client(client):
    d = client.get(f"{BASE_URL}/transfer-methods", params={"kind": "house_land", "state": STATE}).json()
    assert len(d["methods"]) >= 1


# --- organize: nothing saved until confirm
def test_organize_saves_nothing_then_confirm(client, created):
    before = _count(client)
    text = "TEST_I have a house on Maple street, a checking account at Chase ending 4417, a 2019 Ford truck, and my 401k at work."
    r = client.post(f"{BASE_URL}/trust-cases/{CID}/asset-items/organize", json={"text": text}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["items"]) >= 2
    assert d["retirement_left_out"], d
    assert all("401" not in i["description"] for i in d["items"])
    assert _count(client) == before
    r = client.post(f"{BASE_URL}/trust-cases/{CID}/asset-items/confirm", json={"text": text, "items": d["items"]})
    assert r.status_code == 200, r.text
    after = client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"]
    assert len(after) == before + len(d["items"])
    new = after[before:]
    created["items"].extend(i["id"] for i in new)
    assert all(i["source"] == "ai" and i["flags"]["review"] for i in new)
    created["raw_text"] = text


# --- admin views
def test_admin_summary_and_schedule(admin, created):
    s = admin.get(f"{BASE_URL}/admin/trust-cases/{CID}/intake-summary").json()
    assert s["client_state"] == STATE
    if created.get("raw_text"):
        assert any(t["text"] == created["raw_text"] for t in s["original_text"])
    assert isinstance(s["legacy_assets"], list)
    sa = admin.get(f"{BASE_URL}/admin/trust-cases/{CID}/schedule-a").json()
    rows = sa["part_i"] + sa["part_ii"]
    assert any("Elm" in r["description_of_property"] for r in rows)
    assert [r["number"] for r in rows] == list(range(1, len(rows) + 1))
    csv = admin.get(f"{BASE_URL}/admin/trust-cases/{CID}/schedule-a", params={"format": "csv"})
    assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
    assert csv.text.startswith("Part,No.,Description of Property")


def test_admin_endpoints_forbidden_for_client(client):
    assert client.get(f"{BASE_URL}/admin/trust-cases/{CID}/intake-summary").status_code in (401, 403)
    assert client.get(f"{BASE_URL}/admin/trust-cases/{CID}/schedule-a").status_code in (401, 403)
    assert client.get(f"{BASE_URL}/admin/transfer-methods").status_code in (401, 403)


def test_admin_edit_hidden_until_release(admin, client, created):
    r = _add(client, created, description="TEST_Admin edit target", kind="cash")
    iid = r.json()["id"]
    r = admin.put(f"{BASE_URL}/trust-cases/{CID}/asset-items/{iid}", json={"description": "TEST_Admin EDITED", "kind": "cash"})
    assert r.status_code == 200
    a = next(i for i in admin.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"] if i["id"] == iid)
    assert a["description"] == "TEST_Admin EDITED" and a.get("has_unreleased_edits")
    c = next(i for i in client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"] if i["id"] == iid)
    assert c["description"] == "TEST_Admin edit target" and "pending_admin" not in c
    r = admin.post(f"{BASE_URL}/admin/trust-cases/{CID}/asset-items/release").json()
    assert r["released"] >= 1
    c = next(i for i in client.get(f"{BASE_URL}/trust-cases/{CID}/asset-items").json()["items"] if i["id"] == iid)
    assert c["description"] == "TEST_Admin EDITED"


# --- library
def test_library_seed_and_add_confirm(admin, client, created):
    rows = admin.get(f"{BASE_URL}/admin/transfer-methods").json()["rows"]
    generic = [r for r in rows if r["state"] == "ANY"]
    assert len(generic) >= 9
    wording = f"TEST_Deed form {uuid.uuid4().hex[:4]}"
    r = admin.post(f"{BASE_URL}/admin/transfer-methods", json={"kind": "vehicle", "state": "Nevada", "wording": wording, "status": "confirmed"})
    assert r.status_code == 200
    row = r.json()
    created["methods"].append(row["id"])
    assert row["status"] == "needs_check"
    m = client.get(f"{BASE_URL}/transfer-methods", params={"kind": "vehicle", "state": "Nevada"}).json()["methods"]
    assert any(x["wording"] == wording for x in m)
    r = admin.patch(f"{BASE_URL}/admin/transfer-methods/{row['id']}", json={**row, "status": "confirmed"})
    assert r.status_code == 200
    m = client.get(f"{BASE_URL}/transfer-methods", params={"kind": "vehicle", "state": "Nevada"}).json()["methods"]
    assert any(x["wording"] == wording and x["status"] == "confirmed" for x in m)
    bad = admin.post(f"{BASE_URL}/admin/transfer-methods", json={"kind": "zzz", "state": "Nevada", "wording": "abc"})
    assert bad.status_code == 400
