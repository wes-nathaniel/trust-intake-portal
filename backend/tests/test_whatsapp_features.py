"""Tests for WhatsApp inbox, admin commands, and client opt-in features."""
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
ADMIN_WA = "+19545983681"
EXISTING_CASE_ID = "6f96b5b7-084e-43df-af66-aa2022f1417d"
SHORT_ID = EXISTING_CASE_ID[:8]  # 6f96b5b7


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def client_session():
    s = requests.Session()
    email = f"testwa_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "ClientPass123", "name": "WA Tester"})
    assert r.status_code == 200, r.text
    s.email = email
    return s


@pytest.fixture(scope="module")
def owned_case(client_session):
    """A case owned by client_session with a grantor phone."""
    r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    r2 = client_session.post(f"{API}/trust-cases/{cid}/grantors", json={
        "full_legal_name": "Grantor One",
        "date_of_birth": "1980-01-01",
        "ssn": "111-22-3333",
        "address": {"line1": "1 Test St", "city": "Miami", "state": "FL", "zip": "33101"},
        "marital_status": "Single",
        "citizenship": "US",
        "email": client_session.email,
        "phone": "+15550001111",
    })
    assert r2.status_code == 200, r2.text
    return cid


# ---------- STATUS ENDPOINT ----------
def test_whatsapp_status(admin_session):
    r = admin_session.get(f"{API}/admin/whatsapp/status")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["enabled"] is True
    assert d["admin_number"] == ADMIN_WA
    assert d["notify_admin_on_events"] is True


# ---------- INBOUND WEBHOOK ----------
class TestInboundWebhook:
    def test_unknown_sender_creates_inbox_entry(self, admin_session):
        unknown = f"+1555{uuid.uuid4().int % 10000000:07d}"
        r = requests.post(f"{API}/webhooks/twilio/whatsapp-inbound", data={
            "From": f"whatsapp:{unknown}",
            "To": "whatsapp:+14155238886",
            "Body": "Hello, I'm a stranger",
            "ProfileName": "Stranger Danger",
            "MessageSid": f"SM{uuid.uuid4().hex}",
        })
        assert r.status_code == 200
        assert "<Response>" in r.text  # TwiML
        # Now GET inbox and confirm
        r2 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert r2.status_code == 200
        threads = r2.json()["threads"]
        found = [t for t in threads if t["from"] == unknown]
        assert found, f"Expected inbox thread for {unknown}, got {[t['from'] for t in threads]}"
        assert found[0]["profile_name"] == "Stranger Danger"
        assert found[0]["messages"][0]["body"] == "Hello, I'm a stranger"

    def test_known_sender_appended_to_case_thread(self, admin_session, client_session, owned_case):
        # Grantor phone was set to +15550001111 in fixture
        grantor_phone = "+15550001111"
        body_txt = f"Reply from grantor {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/webhooks/twilio/whatsapp-inbound", data={
            "From": f"whatsapp:{grantor_phone}",
            "To": "whatsapp:+14155238886",
            "Body": body_txt,
            "ProfileName": "Grantor",
            "MessageSid": f"SM{uuid.uuid4().hex}",
        })
        assert r.status_code == 200
        # Verify appended to case thread, NOT inbox
        r2 = admin_session.get(f"{API}/admin/trust-cases/{owned_case}/whatsapp-thread")
        assert r2.status_code == 200
        thread = r2.json()["thread"]
        bodies = [m.get("body") for m in thread]
        assert body_txt in bodies
        # Confirm not in inbox
        r3 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        threads = r3.json()["threads"]
        assert not any(t["from"] == grantor_phone for t in threads), \
            "Grantor phone should route to case, not inbox"


# ---------- INBOX ATTACH & ARCHIVE ----------
class TestInboxAttach:
    def test_attach_moves_messages_and_sets_phone(self, admin_session):
        unknown = f"+1555{uuid.uuid4().int % 10000000:07d}"
        # Seed 2 messages
        for i in range(2):
            requests.post(f"{API}/webhooks/twilio/whatsapp-inbound", data={
                "From": f"whatsapp:{unknown}",
                "To": "whatsapp:+14155238886",
                "Body": f"msg {i}",
                "ProfileName": "AttachTest",
                "MessageSid": f"SM{uuid.uuid4().hex}",
            })
        # Attach to existing case
        r = admin_session.post(f"{API}/admin/whatsapp/inbox/attach", json={
            "from_number": unknown,
            "case_id": EXISTING_CASE_ID,
            "save_phone": True,
        })
        assert r.status_code == 200, r.text
        assert r.json()["attached"] == 2
        # Verify inbox no longer returns this sender
        r2 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert not any(t["from"] == unknown for t in r2.json()["threads"])
        # Verify case thread now has these messages
        r3 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}/whatsapp-thread")
        bodies = [m.get("body") for m in r3.json()["thread"]]
        assert "msg 0" in bodies and "msg 1" in bodies
        # Verify client_phone set
        r4 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r4.status_code == 200
        assert r4.json().get("client_phone") == unknown

    def test_attach_unknown_case_404(self, admin_session):
        r = admin_session.post(f"{API}/admin/whatsapp/inbox/attach", json={
            "from_number": "+15550009999",
            "case_id": "nonexistent-case-id",
            "save_phone": False,
        })
        assert r.status_code == 404

    def test_archive_removes_from_inbox(self, admin_session):
        unknown = f"+1555{uuid.uuid4().int % 10000000:07d}"
        requests.post(f"{API}/webhooks/twilio/whatsapp-inbound", data={
            "From": f"whatsapp:{unknown}",
            "To": "whatsapp:+14155238886",
            "Body": "spam",
            "MessageSid": f"SM{uuid.uuid4().hex}",
        })
        # Confirm present
        r = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert any(t["from"] == unknown for t in r.json()["threads"])
        # Archive
        r2 = admin_session.post(f"{API}/admin/whatsapp/inbox/archive",
                                json={"from_number": unknown})
        assert r2.status_code == 200
        assert r2.json()["archived"] >= 1
        # Confirm gone
        r3 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert not any(t["from"] == unknown for t in r3.json()["threads"])

    def test_archive_missing_number_400(self, admin_session):
        r = admin_session.post(f"{API}/admin/whatsapp/inbox/archive", json={})
        assert r.status_code == 400


# ---------- CLIENT OPT-IN ----------
class TestOptIn:
    def test_opt_in_true_sends_welcome_once(self, client_session, admin_session, owned_case):
        # First opt-in -> should create welcome entry
        r = client_session.post(f"{API}/trust-cases/{owned_case}/whatsapp-opt-in",
                                json={"opt_in": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["opt_in"] is True
        # Check thread for welcome
        r2 = admin_session.get(f"{API}/admin/trust-cases/{owned_case}/whatsapp-thread")
        thread = r2.json()["thread"]
        welcomes = [m for m in thread if m.get("system") == "welcome"]
        assert len(welcomes) == 1, f"Expected exactly 1 welcome, got {len(welcomes)}"

        # Second call — must be idempotent (no new welcome)
        r3 = client_session.post(f"{API}/trust-cases/{owned_case}/whatsapp-opt-in",
                                 json={"opt_in": True})
        assert r3.status_code == 200
        r4 = admin_session.get(f"{API}/admin/trust-cases/{owned_case}/whatsapp-thread")
        welcomes2 = [m for m in r4.json()["thread"] if m.get("system") == "welcome"]
        assert len(welcomes2) == 1, "Welcome must not fire twice"

        # Verify case flag set
        r5 = admin_session.get(f"{API}/admin/trust-cases/{owned_case}")
        cd = r5.json()
        assert cd.get("whatsapp_opt_in") is True
        assert cd.get("whatsapp_welcomed_at")

    def test_opt_in_false_no_welcome(self, client_session, admin_session):
        # Fresh case for this test
        r = client_session.post(f"{API}/trust-cases", json={"trust_type": "single"})
        cid = r.json()["id"]
        client_session.post(f"{API}/trust-cases/{cid}/grantors", json={
            "full_legal_name": "G Two",
            "date_of_birth": "1980-01-01",
            "ssn": "111-22-3334",
            "address": {"line1": "1 Test St", "city": "Miami", "state": "FL", "zip": "33101"},
            "marital_status": "Single",
            "citizenship": "US",
            "email": client_session.email,
            "phone": "+15550002222",
        })
        r2 = client_session.post(f"{API}/trust-cases/{cid}/whatsapp-opt-in",
                                 json={"opt_in": False})
        assert r2.status_code == 200
        assert r2.json()["opt_in"] is False
        r3 = admin_session.get(f"{API}/admin/trust-cases/{cid}/whatsapp-thread")
        welcomes = [m for m in r3.json()["thread"] if m.get("system") == "welcome"]
        assert len(welcomes) == 0
        r4 = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        assert r4.json().get("whatsapp_opt_in") is False


# ---------- ADMIN COMMANDS ----------
def _post_admin_cmd(body: str):
    return requests.post(f"{API}/webhooks/twilio/whatsapp-inbound", data={
        "From": f"whatsapp:{ADMIN_WA}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "ProfileName": "Admin",
        "MessageSid": f"SM{uuid.uuid4().hex}",
    })


class TestAdminCommands:
    def _latest_admin_log_reply(self, admin_session, body_contains: str) -> str:
        """Best-effort: fetch admin log via a small delay retry. There's no
        dedicated GET endpoint, so we use the trust-cases collection query
        pattern via an intermediate mongo helper if available. We fallback by
        checking effects instead."""
        # There's no exposed GET, so we rely on side-effects & separate assertions.
        return ""

    def test_whoami_does_not_create_inbox_entry(self, admin_session):
        r = _post_admin_cmd("/whoami")
        assert r.status_code == 200
        # Verify admin number NOT in inbox
        r2 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert not any(t["from"] == ADMIN_WA for t in r2.json()["threads"])

    def test_cases_command(self, admin_session):
        r = _post_admin_cmd("/cases")
        assert r.status_code == 200
        # No inbox entry
        r2 = admin_session.get(f"{API}/admin/whatsapp/inbox")
        assert not any(t["from"] == ADMIN_WA for t in r2.json()["threads"])

    def test_case_info_valid(self, admin_session):
        r = _post_admin_cmd(f"/case {SHORT_ID} info")
        assert r.status_code == 200

    def test_case_status_valid_flips_status(self, admin_session):
        # First set to In Review, verify, then set to Drafting Trust, verify
        r = _post_admin_cmd(f"/case {SHORT_ID} status In Review")
        assert r.status_code == 200
        time.sleep(0.3)
        r2 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r2.status_code == 200
        assert r2.json()["status"] == "In Review"

        # Flip to another valid status
        r3 = _post_admin_cmd(f"/case {SHORT_ID} status Drafting Trust")
        assert r3.status_code == 200
        time.sleep(0.3)
        r4 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r4.json()["status"] == "Drafting Trust"

        # Restore to In Review for later tests
        _post_admin_cmd(f"/case {SHORT_ID} status In Review")

    def test_case_note_appended(self, admin_session):
        marker = f"AutoQA-note-{uuid.uuid4().hex[:6]}"
        r = _post_admin_cmd(f"/case {SHORT_ID} note This is a test {marker}")
        assert r.status_code == 200
        time.sleep(0.3)
        r2 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r2.status_code == 200
        notes = r2.json().get("admin_notes") or []
        matched = [n for n in notes if marker in (n.get("note") or n.get("body") or "")]
        assert matched, f"Expected note containing {marker} in admin_notes"
        # Author field
        assert matched[-1].get("author") == "WhatsApp Admin", \
            f"Author expected 'WhatsApp Admin', got {matched[-1].get('author')}"

    def test_case_unknown_short_id(self, admin_session):
        # Invalid short id - status should not change
        r0 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        original_status = r0.json()["status"]
        r = _post_admin_cmd("/case DEADBEEF info")
        assert r.status_code == 200
        # Status of real case must be unchanged
        r2 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r2.json()["status"] == original_status

    def test_case_bogus_status_does_not_change(self, admin_session):
        r0 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        original_status = r0.json()["status"]
        r = _post_admin_cmd(f"/case {SHORT_ID} status Bogus")
        assert r.status_code == 200
        time.sleep(0.3)
        r2 = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}")
        assert r2.json()["status"] == original_status, \
            "Bogus status must NOT change the case"


# ---------- BACKWARDS COMPAT ----------
class TestBackwardsCompat:
    def test_send_whatsapp_endpoint(self, admin_session):
        r = admin_session.post(
            f"{API}/admin/trust-cases/{EXISTING_CASE_ID}/send-whatsapp",
            json={"body": "Regression check ping"},
        )
        # sandbox may return sent:false; endpoint itself must succeed with 200
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "entry" in d
        assert d["entry"]["body"] == "Regression check ping"

    def test_get_thread_endpoint(self, admin_session):
        r = admin_session.get(f"{API}/admin/trust-cases/{EXISTING_CASE_ID}/whatsapp-thread")
        assert r.status_code == 200
        assert isinstance(r.json().get("thread"), list)
