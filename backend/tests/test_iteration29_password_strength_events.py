# Iteration 29: password strength enforcement, password_events + alerts, admin password history, forgot-reset flow
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("support@igcfirm.com", "Wllorenzo03!")

mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

STATE = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    return s, r


def _wait_alert(event_id, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ev = mdb.password_events.find_one({"id": event_id}, {"_id": 0})
        if ev and ev["alert"].get("channel") != "pending":
            return ev, time.time() - t0
        time.sleep(1)
    return mdb.password_events.find_one({"id": event_id}, {"_id": 0}), time.time() - t0


def _latest_event(user_id, kind):
    return mdb.password_events.find_one({"user_id": user_id, "kind": kind}, {"_id": 0}, sort=[("created_at", -1)])


@pytest.fixture(scope="module")
def admin():
    s, r = _login(*ADMIN)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    return s


@pytest.fixture(scope="module")
def client_user():
    email = f"test_pw29_{uuid.uuid4().hex[:8]}@igchq-test.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "StartPass99", "name": "TEST Pw29 Client"})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": email})
    STATE.update(email=email, pw="StartPass99", uid=u["id"])
    yield s
    # cleanup
    mdb.password_events.delete_many({"user_id": u["id"]})
    mdb.trust_cases.delete_many({"client_id": u["id"]})
    mdb.password_reset_tokens.delete_many({"user_id": u["id"]})
    mdb.users.delete_one({"id": u["id"]})


# --- Strength scoring on change-password ---
class TestStrength:
    @pytest.mark.parametrize("weak", ["password1", "abcdefgh1", "aaaaaaaaA1"])
    def test_weak_rejected(self, client_user, weak):
        r = client_user.post(f"{API}/auth/change-password", json={"current_password": STATE["pw"], "new_password": weak})
        assert r.status_code == 400, r.text
        assert "too weak" in r.json()["detail"].lower()

    def test_good_accepted_and_event_email(self, client_user):
        r = client_user.post(f"{API}/auth/change-password", json={"current_password": STATE["pw"], "new_password": "Abcdefg1"})
        assert r.status_code == 200, r.text
        STATE["pw"] = "Abcdefg1"
        ev = _latest_event(STATE["uid"], "client_changed")
        assert ev and ev["actor_email"] == STATE["email"]
        ev, dt = _wait_alert(ev["id"], 20)
        print("no-phone alert", ev["alert"], f"{dt:.1f}s")
        assert ev["alert"]["channel"] == "email"
        assert ev["alert"]["whatsapp_attempted"] is False

    def test_strong_accepted(self, client_user):
        r = client_user.post(f"{API}/auth/change-password", json={"current_password": STATE["pw"], "new_password": "NewPass12345"})
        assert r.status_code == 200, r.text
        STATE["pw"] = "NewPass12345"
        s, r = _login(STATE["email"], "NewPass12345")
        assert r.status_code == 200


# --- Temp password + WhatsApp fallback + history ---
class TestTempAndHistory:
    def test_create_case_with_invalid_phone(self, client_user):
        r = client_user.post(f"{API}/trust-cases", json={"trust_type": "single", "trust_name": "TEST Pw29 Trust", "client_phone": "+15005550001"})
        assert r.status_code in (200, 201), r.text
        STATE["case_id"] = r.json()["id"]

    def test_history_auth(self, admin, client_user):
        assert client_user.get(f"{API}/admin/trust-cases/{STATE['case_id']}/password-history").status_code == 403
        assert admin.get(f"{API}/admin/trust-cases/nonexistent-xyz/password-history").status_code == 404

    def test_temp_password_whatsapp_fallback(self, admin):
        r = admin.post(f"{API}/admin/users/temp-password", json={"email": STATE["email"]})
        assert r.status_code == 200, r.text
        STATE["temp"] = r.json()["temp_password"]
        ev = _latest_event(STATE["uid"], "temp_password_set")
        assert ev["actor_email"] == ADMIN[0]
        assert ev["alert"]["channel"] == "pending"
        ev, dt = _wait_alert(ev["id"], 45)
        print("invalid-phone alert", ev["alert"], f"{dt:.1f}s")
        assert ev["alert"]["channel"] == "email", ev["alert"]
        # Iteration 30: client WhatsApp disabled (CLIENT_WHATSAPP_ENABLED=False) -> never attempted
        assert ev["alert"]["whatsapp_attempted"] is False

    def test_history_rows_newest_first(self, admin):
        r = admin.get(f"{API}/admin/trust-cases/{STATE['case_id']}/password-history")
        assert r.status_code == 200
        rows = r.json()["rows"]
        kinds = [x["kind"] for x in rows]
        print(kinds)
        assert kinds[0] == "temp_password_set"
        assert kinds.count("client_changed") == 2
        ts = [x["created_at"] for x in rows]
        assert ts == sorted(ts, reverse=True)
        assert all(set(x.keys()) <= {"kind", "actor_email", "created_at", "alert"} for x in rows)

    def test_forced_change_flow(self):
        s, r = _login(STATE["email"], STATE["temp"])
        assert r.status_code == 200, r.text
        me = s.get(f"{API}/auth/me").json()
        assert me.get("requires_password_change") is True, me
        r = s.post(f"{API}/auth/change-password", json={"current_password": STATE["temp"], "new_password": "weakpass"})
        assert r.status_code == 400
        r = s.post(f"{API}/auth/change-password", json={"current_password": STATE["temp"], "new_password": "Forced!Pass29"})
        assert r.status_code == 200, r.text
        assert r.json()["user"].get("requires_password_change") in (False, None)
        STATE["pw"] = "Forced!Pass29"


# --- Forgot password -> reset ---
class TestForgotReset:
    def test_forgot_reset_flow(self, admin):
        # set temp first so we can confirm reset clears requires_password_change
        assert admin.post(f"{API}/admin/users/temp-password", json={"email": STATE["email"]}).status_code == 200
        r = requests.post(f"{API}/auth/forgot-password", json={"email": STATE["email"]})
        assert r.status_code == 200
        tok = mdb.password_reset_tokens.find_one({"user_id": STATE["uid"], "used": False}, sort=[("created_at", -1)])
        assert tok
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok["token"], "password": "password1"})
        assert r.status_code == 400 and "too weak" in r.json()["detail"].lower()
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok["token"], "password": "Reset!Pass29x"})
        assert r.status_code == 200, r.text
        u = mdb.users.find_one({"id": STATE["uid"]})
        assert u.get("requires_password_change") is False
        ev = _latest_event(STATE["uid"], "forgot_reset")
        assert ev and ev["actor_email"] == STATE["email"]
        # token reuse rejected
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok["token"], "password": "Another!Pass29"})
        assert r.status_code == 400
        s, r = _login(STATE["email"], "Reset!Pass29x")
        assert r.status_code == 200
        ev, dt = _wait_alert(ev["id"], 45)
        print("forgot alert", ev["alert"], f"{dt:.1f}s")
        assert ev["alert"]["channel"] in ("email", "whatsapp")
