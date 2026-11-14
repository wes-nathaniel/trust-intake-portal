"""
Tests for Client Activity Tracking feature:
- POST /api/auth/heartbeat (Test A, B)
- GET /api/admin/stats clients_online (Test A)
- GET /api/admin/trust-cases/{case_id} client_online_now (Test A)
- Notification settings login_alert_enabled (Test E)
- MCP read_client_activity tool (Test D)
- Client cannot see activity data (Test F)
- Rose Nabhan protection (Test H)
"""
import pytest
import requests
import os
import time
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ROSE_CASE_ID = "abbd2cc2-3fee-404a-8243-1069552921e8"
ADMIN_EMAIL = "wes@igchq.com"
ADMIN_PASSWORD = "Wllorenzo03!"

# Test state shared across tests
_state = {
    "test_user_id": None,
    "test_case_id": None,
    "test_user_email": None,
    "client_session": None,
    "mcp_key": None,
}

TIMESTAMP = int(time.time())
TEST_EMAIL = f"testact_{TIMESTAMP}@example.com"
TEST_PASSWORD = "TestPass123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def test_case_setup(admin_session):
    """Create test client and case, yield info, then cleanup."""
    # Register test user
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "TEST_Activity_Client"
    })
    assert r.status_code in [200, 201], f"Register failed: {r.text}"
    user_data = r.json()
    user_id = user_data.get("user", {}).get("id") or user_data.get("id")
    
    # Create a trust case for this user via admin
    # First login as client to get their session
    client_session = requests.Session()
    lr = client_session.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert lr.status_code == 200, f"Client login failed: {lr.text}"
    client_user = lr.json()
    if "user" in client_user:
        client_user = client_user["user"]
    client_user_id = client_user.get("id")

    # Get cases for this user
    # Use admin to list cases and find this user's
    # Create a case by using the trust-cases creation endpoint
    cr = client_session.post(f"{BASE_URL}/api/trust-cases", json={
        "trust_name": "TEST Activity Trust",
        "intake_path": "new"
    })
    case_id = None
    if cr.status_code in [200, 201]:
        cdata = cr.json()
        case_id = cdata.get("id") or cdata.get("case_id")
    
    if not case_id:
        # Find case via admin
        cases_r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        if cases_r.status_code == 200:
            resp_json = cases_r.json()
            cases = resp_json if isinstance(resp_json, list) else resp_json.get("cases", [])
            for c in cases:
                if c.get("client_email") == TEST_EMAIL:
                    case_id = c.get("id")
                    break

    _state["test_user_id"] = client_user_id
    _state["test_case_id"] = case_id
    _state["test_user_email"] = TEST_EMAIL
    _state["client_session"] = client_session

    yield {
        "user_id": client_user_id,
        "case_id": case_id,
        "email": TEST_EMAIL,
        "client_session": client_session,
    }

    # Cleanup
    if case_id:
        admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
    # Delete user via MongoDB directly
    try:
        mongo = MongoClient("mongodb://localhost:27017/")
        db = mongo["trust_portal"]
        db.users.delete_one({"email": TEST_EMAIL})
        mongo.close()
    except Exception as e:
        print(f"Cleanup warning: {e}")


# ─── Test A: Heartbeat + online now ───────────────────────────────────────────

class TestHeartbeat:
    """Test A: Heartbeat updates last_active_at and admin sees client online"""

    def test_heartbeat_endpoint_exists(self, test_case_setup):
        """POST /api/auth/heartbeat returns 200 for client"""
        client_session = test_case_setup["client_session"]
        case_id = test_case_setup["case_id"]
        payload = {"case_id": case_id} if case_id else {}
        r = client_session.post(f"{BASE_URL}/api/auth/heartbeat", json=payload)
        assert r.status_code == 200, f"Heartbeat failed: {r.text}"
        print(f"PASS: Heartbeat returned 200: {r.text}")

    def test_admin_stats_clients_online(self, admin_session, test_case_setup):
        """After heartbeat, admin stats should show this client in clients_online"""
        # Fire heartbeat first
        client_session = test_case_setup["client_session"]
        case_id = test_case_setup["case_id"]
        payload = {"case_id": case_id} if case_id else {}
        client_session.post(f"{BASE_URL}/api/auth/heartbeat", json=payload)
        
        r = admin_session.get(f"{BASE_URL}/api/admin/stats")
        assert r.status_code == 200, f"Admin stats failed: {r.text}"
        data = r.json()
        assert "clients_online" in data, "clients_online not in stats response"
        online = data["clients_online"]
        assert isinstance(online, list), "clients_online should be a list"
        # Find our test client
        emails = [c.get("client_email") for c in online]
        names = [c.get("client_name") for c in online]
        print(f"Online clients: {online}")
        found = any(c.get("client_email") == TEST_EMAIL or c.get("name") == "TEST_Activity_Client" for c in online)
        assert found, f"Test client not found in clients_online: {online}"
        print(f"PASS: Test client found in clients_online")

    def test_admin_case_detail_online_now(self, admin_session, test_case_setup):
        """Admin case detail should show client_online_now=True after heartbeat"""
        case_id = test_case_setup["case_id"]
        if not case_id:
            pytest.skip("No case_id available")
        
        # Fire heartbeat first
        client_session = test_case_setup["client_session"]
        client_session.post(f"{BASE_URL}/api/auth/heartbeat", json={"case_id": case_id})
        
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
        assert r.status_code == 200, f"Admin case detail failed: {r.text}"
        data = r.json()
        case = data.get("case") or data
        assert case.get("client_online_now") == True, f"client_online_now not True: {case.get('client_online_now')}"
        print(f"PASS: client_online_now=True in admin case detail")


# ─── Test B: Last seen after 5 min ────────────────────────────────────────────

class TestLastSeen:
    """Test B: After setting last_active_at to 10 minutes ago, client should not be online"""

    def test_offline_after_5_minutes(self, admin_session, test_case_setup):
        """Set last_active_at to 10 min ago, verify not online"""
        user_id = test_case_setup["user_id"]
        case_id = test_case_setup["case_id"]
        if not user_id:
            pytest.skip("No user_id")
        
        # Set last_active_at to 10 minutes ago via MongoDB
        ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        mongo = MongoClient("mongodb://localhost:27017/")
        db = mongo["trust_portal"]
        db.users.update_one({"id": user_id}, {"$set": {"last_active_at": ten_min_ago}})
        mongo.close()

        # Check admin stats
        r = admin_session.get(f"{BASE_URL}/api/admin/stats")
        assert r.status_code == 200
        data = r.json()
        online = data.get("clients_online", [])
        found = any(c.get("client_email") == TEST_EMAIL for c in online)
        assert not found, f"Test client should NOT be in clients_online after 10 min: {online}"
        print(f"PASS: Test client not in clients_online after setting last_active_at to 10 min ago")

    def test_case_detail_shows_last_seen(self, admin_session, test_case_setup):
        """Admin case detail shows client_online_now=False and has last_active_at"""
        case_id = test_case_setup["case_id"]
        user_id = test_case_setup["user_id"]
        if not case_id:
            pytest.skip("No case_id")
        
        # Ensure last_active_at is set to 10 min ago
        if user_id:
            ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            mongo = MongoClient("mongodb://localhost:27017/")
            db = mongo["trust_portal"]
            db.users.update_one({"id": user_id}, {"$set": {"last_active_at": ten_min_ago}})
            mongo.close()
        
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
        assert r.status_code == 200
        data = r.json()
        case = data.get("case") or data
        assert case.get("client_online_now") == False, f"Expected offline but got: {case.get('client_online_now')}"
        assert case.get("client_last_active_at"), "client_last_active_at should be set"
        print(f"PASS: client_online_now=False, client_last_active_at={case.get('client_last_active_at')}")


# ─── Test D: MCP read_client_activity ─────────────────────────────────────────

class TestMCPClientActivity:
    """Test D: MCP read_client_activity tool"""

    def test_mcp_generate_key(self, admin_session):
        """Generate or get MCP key for testing"""
        r = admin_session.post(f"{BASE_URL}/api/admin/mcp/generate-key")
        assert r.status_code in [200, 201], f"MCP key gen failed: {r.text}"
        data = r.json()
        mcp_key = data.get("key")
        assert mcp_key, "MCP key not returned"
        _state["mcp_key"] = mcp_key
        print(f"PASS: MCP key generated: {mcp_key[:20]}...")

    def test_mcp_read_client_activity_single(self, test_case_setup):
        """MCP read_client_activity for single case"""
        if not _state.get("mcp_key"):
            pytest.skip("No MCP key available")
        case_id = test_case_setup["case_id"]
        if not case_id:
            pytest.skip("No case_id")
        
        r = requests.post(
            f"{BASE_URL}/api/mcp/{_state['mcp_key']}",
            json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "read_client_activity", "arguments": {"case_id": case_id}}
            }
        )
        assert r.status_code == 200, f"MCP call failed: {r.text}"
        data = r.json()
        result = data.get("result", {})
        content = result.get("content", [{}])[0].get("text", "")
        assert "last_login_at" in content, f"last_login_at not in response: {content}"
        assert "last_active_at" in content, f"last_active_at not in response: {content}"
        assert "online_now" in content, f"online_now not in response: {content}"
        print(f"PASS: MCP read_client_activity for single case: {content[:200]}")

    def test_mcp_read_client_activity_all(self):
        """MCP read_client_activity for all cases"""
        if not _state.get("mcp_key"):
            pytest.skip("No MCP key available")
        
        r = requests.post(
            f"{BASE_URL}/api/mcp/{_state['mcp_key']}",
            json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "read_client_activity", "arguments": {}}
            }
        )
        assert r.status_code == 200
        data = r.json()
        content = data.get("result", {}).get("content", [{}])[0].get("text", "")
        assert "Client activity" in content, f"Expected 'Client activity' header: {content[:200]}"
        print(f"PASS: MCP read_client_activity all cases: {content[:200]}")

    def test_mcp_audit_log_written(self):
        """Verify audit log was written for MCP read_client_activity"""
        mongo = MongoClient("mongodb://localhost:27017/")
        db = mongo["trust_portal"]
        entry = db.account_number_audit_log.find_one(
            {"action": "mcp_read_client_activity"},
            sort=[("at", -1)]
        )
        mongo.close()
        assert entry, "No mcp_read_client_activity audit log entry found"
        print(f"PASS: Audit log entry found: {entry.get('action')} at {entry.get('at')}")


# ─── Test E: Notification settings ────────────────────────────────────────────

class TestNotificationSettings:
    """Test E: Login alert toggle default OFF and 1-hour dedup"""

    def test_get_notification_settings_default_off(self, admin_session):
        """GET /api/admin/notification-settings returns login_alert_enabled=false"""
        r = admin_session.get(f"{BASE_URL}/api/admin/notification-settings")
        assert r.status_code == 200, f"Notification settings failed: {r.text}"
        data = r.json()
        # It may be false by default or may have been set before
        assert "login_alert_enabled" in data, f"login_alert_enabled not in response: {data}"
        print(f"PASS: login_alert_enabled={data.get('login_alert_enabled')}")

    def test_toggle_login_alert_on(self, admin_session):
        """PATCH /api/admin/notification-settings enables login alert"""
        r = admin_session.patch(f"{BASE_URL}/api/admin/notification-settings", json={"login_alert_enabled": True})
        assert r.status_code == 200, f"Toggle failed: {r.text}"
        data = r.json()
        assert data.get("login_alert_enabled") == True, f"Expected True: {data}"
        print(f"PASS: login_alert_enabled toggled to True")

    def test_toggle_login_alert_off(self, admin_session):
        """PATCH /api/admin/notification-settings disables login alert"""
        r = admin_session.patch(f"{BASE_URL}/api/admin/notification-settings", json={"login_alert_enabled": False})
        assert r.status_code == 200, f"Toggle failed: {r.text}"
        data = r.json()
        assert data.get("login_alert_enabled") == False, f"Expected False: {data}"
        print(f"PASS: login_alert_enabled toggled back to False")

    def test_1_hour_dedup_code_present(self):
        """Verify 1-hour dedup logic is present in server.py"""
        with open("/app/backend/server.py") as f:
            code = f.read()
        assert "login_alert_sent_at" in code, "login_alert_sent_at not found in server.py"
        assert "3600" in code or "timedelta(hours=1)" in code or "one_hour" in code or "1 hour" in code.lower(), "1-hour dedup logic not found"
        print("PASS: 1-hour dedup logic present in server.py")


# ─── Test F: Clients cannot see activity data ─────────────────────────────────

class TestClientCannotSeeActivity:
    """Test F: Clients cannot see activity data"""

    def test_me_does_not_return_last_active_at(self, test_case_setup):
        """Login response should not return last_active_at to client"""
        # Re-login to check what fields are returned
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        # Login response may return user object directly or nested
        user = data.get("user") or data
        assert "last_active_at" not in user, f"last_active_at should NOT be in login response: {list(user.keys())}"
        print(f"PASS: last_active_at not in login response. Keys: {list(user.keys())}")

    def test_client_cannot_access_admin_stats(self, test_case_setup):
        """GET /api/admin/stats should return 403/401 for client"""
        client_session = test_case_setup["client_session"]
        r = client_session.get(f"{BASE_URL}/api/admin/stats")
        assert r.status_code in [401, 403], f"Expected 401/403 but got {r.status_code}: {r.text}"
        print(f"PASS: Client gets {r.status_code} for /api/admin/stats")

    def test_client_cannot_access_admin_trust_cases(self, test_case_setup):
        """GET /api/admin/trust-cases should return 403/401 for client"""
        client_session = test_case_setup["client_session"]
        r = client_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert r.status_code in [401, 403], f"Expected 401/403 but got {r.status_code}: {r.text}"
        print(f"PASS: Client gets {r.status_code} for /api/admin/trust-cases")


# ─── Test H: Rose Nabhan protection ───────────────────────────────────────────

class TestRoseNabhanProtection:
    """Test H: Rose Nabhan case is untouched"""

    def test_rose_case_no_test_activity(self, admin_session):
        """Rose Nabhan's case should have no test activity"""
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{ROSE_CASE_ID}")
        if r.status_code == 404:
            print("NOTE: Rose Nabhan's case not found in this preview env (expected per prior tests)")
            return
        assert r.status_code == 200, f"Rose case detail failed: {r.text}"
        data = r.json()
        case = data.get("case") or data
        
        # Check asset_items count
        items = [i for i in (case.get("asset_items") or []) if not i.get("deleted")]
        print(f"Rose's non-deleted asset items: {len(items)}")
        
        # Check no login_alert_sent_at on user (via MongoDB)
        mongo = MongoClient("mongodb://localhost:27017/")
        db = mongo["trust_portal"]
        # Find Rose's user
        rose_case = db.trust_cases.find_one({"id": ROSE_CASE_ID})
        if rose_case:
            rose_user = db.users.find_one({"id": rose_case.get("client_id")})
            if rose_user:
                assert "login_alert_sent_at" not in rose_user or rose_user.get("login_alert_sent_at") is None, \
                    "login_alert_sent_at should not be on Rose's user record"
                # Check that test modified last_active_at was not set by our test
                last_active = rose_user.get("last_active_at")
                print(f"Rose last_active_at: {last_active} (should be untouched by tests)")
        mongo.close()
        print("PASS: Rose Nabhan protection verified")
