# Iteration 33: "Release to client for review" - internal vs client status, held draft/asset edits,
# release now/silent/schedule, scheduled snapshot + changed warning, email suppression, removed endpoints.
import io
import os
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from reportlab.pdfgen import canvas

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
NY = ZoneInfo("America/New_York")
ADMIN = {"email": "support@igcfirm.com", "password": "Wllorenzo03!"}


def _pdf(text="TEST trust draft Article I"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    return s


def _new_client():
    s = requests.Session()
    email = f"test_release_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test12345!Aa", "name": "TEST Release Client"})
    assert r.status_code in (200, 201), r.text
    r = s.post(f"{API}/trust-cases", json={"trust_type": "single"})
    assert r.status_code in (200, 201), r.text
    return s, r.json()["id"], email


@pytest.fixture(scope="module")
def client_case():
    return _new_client()


def _set_status(admin, cid, st):
    r = admin.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": st})
    assert r.status_code == 200, r.text
    return r


# --- internal status change does not change what client sees
class TestInternalStatus:
    def test_status_change_internal_only(self, admin, client_case):
        cs, cid, _ = client_case
        before = cs.get(f"{API}/trust-cases/{cid}").json()["status"]
        _set_status(admin, cid, "Drafting Trust")
        assert admin.get(f"{API}/trust-cases/{cid}").json()["status"] == "Drafting Trust"
        assert cs.get(f"{API}/trust-cases/{cid}").json()["status"] == before
        assert cs.get(f"{API}/trust-cases/{cid}/status").json()["status"] == before
        mine = [c for c in cs.get(f"{API}/trust-cases/mine").json() if c["id"] == cid]
        assert mine and mine[0]["status"] == before

    def test_preview_fields(self, admin, client_case):
        _, cid, email = client_case
        p = admin.get(f"{API}/admin/trust-cases/{cid}/release").json()
        assert p["internal_status"] == "Drafting Trust"
        assert p["client_status"] != "Drafting Trust"
        for k in ("draft_held", "asset_edits_held", "subject", "message", "scheduled_release", "changed_since_scheduled", "history"):
            assert k in p
        assert p["client_email"] == email
        assert "\u2014" not in p["message"] and "\u2013" not in p["message"]
        assert "\u2014" not in p["subject"] and "\u2013" not in p["subject"]


# --- held draft + asset edits, then silent release
class TestHeldAndSilent:
    def test_draft_held_hidden_from_client(self, admin, client_case):
        cs, cid, _ = client_case
        r = admin.post(f"{API}/admin/trust-cases/{cid}/trust-draft",
                       files={"file": ("TEST_draft.pdf", _pdf(), "application/pdf")})
        assert r.status_code == 200, r.text
        _set_status(admin, cid, "Ready for Client Review")
        c = cs.get(f"{API}/trust-cases/{cid}").json()
        assert "trust_draft" not in c and "trust_page_explanations" not in c
        assert admin.get(f"{API}/admin/trust-cases/{cid}/release").json()["draft_held"] is True

    def test_review_ack_blocked_before_release(self, admin, client_case):
        cs, cid, _ = client_case
        r = cs.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"review_completed_ack": True})
        assert r.status_code == 400

    def test_asset_edit_held(self, admin, client_case):
        cs, cid, _ = client_case
        r = cs.post(f"{API}/trust-cases/{cid}/asset-items", json={"description": "TEST Blue house", "kind": "house_land", "state": "FL"})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        r = admin.put(f"{API}/trust-cases/{cid}/asset-items/{iid}", json={"description": "TEST Blue house EDITED", "kind": "house_land", "state": "FL"})
        assert r.status_code == 200, r.text
        items = cs.get(f"{API}/trust-cases/{cid}/asset-items").json()["items"]
        assert [i for i in items if i["id"] == iid][0]["description"] == "TEST Blue house"
        assert admin.get(f"{API}/admin/trust-cases/{cid}/release").json()["asset_edits_held"] == 1
        pytest.item_id = iid

    def test_release_silent(self, admin, client_case):
        cs, cid, _ = client_case
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "silent"})
        assert r.status_code == 200, r.text
        rel = r.json()["release"]
        assert rel["emailed"] is False and rel["draft_released"] is True and rel["assets_released"] == 1
        c = cs.get(f"{API}/trust-cases/{cid}").json()
        assert c["status"] == "Ready for Client Review"
        assert c.get("trust_draft", {}).get("released") is True
        items = cs.get(f"{API}/trust-cases/{cid}/asset-items").json()["items"]
        assert [i for i in items if i["id"] == pytest.item_id][0]["description"] == "TEST Blue house EDITED"
        p = admin.get(f"{API}/admin/trust-cases/{cid}/release").json()
        assert p["client_status"] == p["internal_status"] and p["draft_held"] is False and p["asset_edits_held"] == 0
        assert p["history"][0]["mode"] == "silent"


# --- release now with email
class TestReleaseNow:
    def test_now_missing_subject_400(self, admin, client_case):
        _, cid, _ = client_case
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "now", "subject": "", "message": "hi"})
        assert r.status_code == 400

    def test_now_ok(self, admin, client_case):
        cs, cid, _ = client_case
        _set_status(admin, cid, "Ready for Payment")
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "now", "subject": "TEST subj", "message": "TEST body"})
        assert r.status_code == 200, r.text
        rel = r.json()["release"]
        assert rel["email_requested"] is True and isinstance(rel["emailed"], bool)
        assert cs.get(f"{API}/trust-cases/{cid}/status").json()["status"] == "Ready for Payment"


# --- schedule, changed warning, update, cancel
class TestSchedule:
    def test_past_time_400(self, admin, client_case):
        _, cid, _ = client_case
        past = (datetime.now(NY) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": past, "send_email": False})
        assert r.status_code == 400

    def test_bad_time_400(self, admin, client_case):
        _, cid, _ = client_case
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": "garbage", "send_email": False})
        assert r.status_code == 400

    def test_schedule_change_update_cancel(self, admin, client_case):
        cs, cid, _ = client_case
        _set_status(admin, cid, "Pending Payment Verification")
        fut = (datetime.now(NY) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": fut, "send_email": False})
        assert r.status_code == 200, r.text
        assert r.json()["scheduled"]["snapshot"]["status"] == "Pending Payment Verification"
        p = admin.get(f"{API}/admin/trust-cases/{cid}/release").json()
        assert p["scheduled_release"] and p["changed_since_scheduled"] == []
        _set_status(admin, cid, "Payment Verified")
        p = admin.get(f"{API}/admin/trust-cases/{cid}/release").json()
        assert len(p["changed_since_scheduled"]) >= 1
        assert cs.get(f"{API}/trust-cases/{cid}/status").json()["status"] == "Ready for Payment"
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release/scheduled/update")
        assert r.status_code == 200 and r.json()["scheduled"]["snapshot"]["status"] == "Payment Verified"
        assert admin.get(f"{API}/admin/trust-cases/{cid}/release").json()["changed_since_scheduled"] == []
        r = admin.delete(f"{API}/admin/trust-cases/{cid}/release/scheduled")
        assert r.status_code == 200
        assert admin.get(f"{API}/admin/trust-cases/{cid}/release").json()["scheduled_release"] is None
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release/scheduled/update")
        assert r.status_code == 404

    def test_client_cannot_call_release(self, client_case):
        cs, cid, _ = client_case
        assert cs.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "silent"}).status_code in (401, 403)
        assert cs.get(f"{API}/admin/trust-cases/{cid}/release").status_code in (401, 403)

    def test_release_404_unknown_case(self, admin):
        assert admin.get(f"{API}/admin/trust-cases/nope-{uuid.uuid4().hex}/release").status_code == 404


# --- review ack only when RELEASED status is Ready for Client Review
class TestReviewAckReleased:
    def test_ack_uses_released_status(self, admin):
        cs, cid, _ = _new_client()
        admin.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files={"file": ("TEST_d.pdf", _pdf(), "application/pdf")})
        _set_status(admin, cid, "Ready for Client Review")
        admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "silent"})
        _set_status(admin, cid, "Drafting Trust")  # internal moves back, client still sees RFCR
        assert cs.get(f"{API}/trust-cases/{cid}/status").json()["status"] == "Ready for Client Review"
        r = cs.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"review_completed_ack": True})
        assert r.status_code == 200, r.text


# --- removed legacy endpoints
class TestRemovedEndpoints:
    @pytest.mark.parametrize("path", ["release-trust-draft", "resend-status-email", "asset-items/release"])
    def test_removed(self, admin, client_case, path):
        _, cid, _ = client_case
        r = admin.post(f"{API}/admin/trust-cases/{cid}/{path}", json={})
        assert r.status_code in (404, 405), f"{path} -> {r.status_code}"


# --- client JSON must not leak admin-only release data (scheduled snapshot / history)
class TestClientLeak:
    def test_no_scheduled_or_history_leak(self, admin):
        cs, cid, _ = _new_client()
        _set_status(admin, cid, "Drafting Trust")
        fut = (datetime.now(NY) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": fut, "subject": "S", "message": "M"})
        c = cs.get(f"{API}/trust-cases/{cid}").json()
        mine = [x for x in cs.get(f"{API}/trust-cases/mine").json() if x["id"] == cid][0]
        admin.delete(f"{API}/admin/trust-cases/{cid}/release/scheduled")
        assert "scheduled_release" not in c and "scheduled_release" not in mine, "scheduled_release leaks to client"

    def test_no_pending_admin_leak(self, admin):
        cs, cid, _ = _new_client()
        iid = cs.post(f"{API}/trust-cases/{cid}/asset-items", json={"description": "TEST car", "kind": "vehicle", "state": "FL"}).json()["id"]
        admin.put(f"{API}/trust-cases/{cid}/asset-items/{iid}", json={"description": "TEST car HELD EDIT", "kind": "vehicle", "state": "FL"})
        c = cs.get(f"{API}/trust-cases/{cid}").json()
        assert "HELD EDIT" not in str(c.get("asset_items")), "held admin asset edit (pending_admin) leaks in client case JSON"


# --- Iteration 34 retest: release_history leak, schedule with send_email false, send-for-signing no client email
class TestIter34:
    def test_no_release_history_leak_after_release(self, admin):
        cs, cid, _ = _new_client()
        _set_status(admin, cid, "Drafting Trust")
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "silent"})
        assert r.status_code == 200, r.text
        assert admin.get(f"{API}/trust-cases/{cid}").json().get("release_history"), "admin should see history"
        c = cs.get(f"{API}/trust-cases/{cid}").json()
        mine = [x for x in cs.get(f"{API}/trust-cases/mine").json() if x["id"] == cid][0]
        assert c["status"] == "Drafting Trust"
        for d in (c, mine):
            assert "release_history" not in d and "scheduled_release" not in d

    def test_schedule_without_email(self, admin):
        cs, cid, _ = _new_client()
        _set_status(admin, cid, "Drafting Trust")
        fut = (datetime.now(NY) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        r = admin.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": fut, "send_email": False})
        assert r.status_code == 200, r.text
        sr = admin.get(f"{API}/admin/trust-cases/{cid}/release").json()["scheduled_release"]
        assert sr and sr.get("send_email") is False
        assert cs.get(f"{API}/trust-cases/{cid}").json()["status"] != "Drafting Trust"
        admin.delete(f"{API}/admin/trust-cases/{cid}/release/scheduled")

    def test_send_for_signing_no_crash(self, admin):
        cs, cid, email = _new_client()
        r = admin.post(f"{API}/admin/trust-cases/{cid}/send-for-signing",
                       data={"signer_email": email, "signer_name": "TEST"},
                       files={"file": ("t.pdf", _pdf(), "application/pdf")})
        assert r.status_code in (200, 400, 422, 503), r.text
