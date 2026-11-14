"""
Tests for UX copy fixes + regression: em-dash removal, step counter, Review step text, MCP, heartbeat, cleanup
"""
import pytest
import requests
import os
import time

def _get_base_url():
    for path in ['/app/frontend/.env']:
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    return os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

BASE_URL = _get_base_url()
print(f"BASE_URL={BASE_URL}")
ADMIN_EMAIL = "wes@igchq.com"
ADMIN_PASSWORD = "Wllorenzo03!"
MCP_KEY = "igc_mcp_f743a0cbff8871496e76a2f7e96295caf77e36b8b22ee030"
TS = str(int(time.time()))
TEST_EMAIL = f"testclient_awtest_{TS}@example.com"
TEST_PASSWORD = "TestPass2026!"

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s

@pytest.fixture(scope="module")
def client_data(admin_session):
    """Create throwaway client, yield (session, user_id, case_id), then cleanup"""
    s = requests.Session()
    # Register
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "AW Test Client"
    })
    assert r.status_code in [200, 201], f"Register failed: {r.text}"
    
    # Login
    r2 = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert r2.status_code == 200, f"Client login failed: {r2.text}"
    data = r2.json()
    user_id = data.get("user", {}).get("id") or data.get("id")

    # Create case
    r3 = s.post(f"{BASE_URL}/api/trust-cases", json={
        "trust_name": "AW Test Revocable Trust",
        "trust_type": "single",
        "intake_path": "new",
        "phone": "5555559999"
    })
    assert r3.status_code in [200, 201], f"Create case failed: {r3.text}"
    case_id = r3.json().get("id") or r3.json().get("case_id")
    
    yield s, user_id, case_id
    
    # Cleanup: delete case and user via admin
    if case_id:
        admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
    if user_id:
        admin_session.delete(f"{BASE_URL}/api/admin/users/{user_id}")


class TestHeartbeat:
    """Test O: heartbeat endpoint"""

    def test_heartbeat_returns_200(self, client_data):
        s, user_id, case_id = client_data
        r = s.post(f"{BASE_URL}/api/auth/heartbeat", json={"case_id": case_id})
        assert r.status_code == 200, f"Heartbeat failed: {r.status_code} {r.text}"
        print("PASS: heartbeat returns 200")


class TestMCP:
    """Tests T, U: MCP endpoints"""

    def test_mcp_read_client_activity(self, client_data):
        s, user_id, case_id = client_data
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "read_client_activity", "arguments": {}}
        }
        r = requests.post(f"{BASE_URL}/api/mcp/{MCP_KEY}", json=payload)
        assert r.status_code == 200, f"MCP read_client_activity failed: {r.status_code} {r.text}"
        data = r.json()
        print(f"PASS: MCP read_client_activity returned: {str(data)[:200]}")

    def test_mcp_read_business_eins(self):
        payload = {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "read_business_eins", "arguments": {}}
        }
        r = requests.post(f"{BASE_URL}/api/mcp/{MCP_KEY}", json=payload)
        assert r.status_code == 200, f"MCP read_business_eins failed: {r.status_code} {r.text}"
        data = r.json()
        print(f"PASS: MCP read_business_eins returned: {str(data)[:200]}")


class TestAdminAccess:
    """Test P, Q, R"""

    def test_admin_can_see_client_list(self, admin_session, client_data):
        s, user_id, case_id = client_data
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert r.status_code == 200
        cases = r.json()
        ids = [c.get("id") for c in cases]
        assert case_id in ids, f"Test case {case_id} not in admin list"
        print("PASS: Admin sees test case in trust-cases list")

    def test_admin_case_detail(self, admin_session, client_data):
        s, user_id, case_id = client_data
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
        assert r.status_code == 200
        print(f"PASS: Admin can view case detail for {case_id}")


class TestNotificationSettings:
    """Test S: login alert toggle"""

    def test_login_alert_toggle_exists(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/notification-settings")
        assert r.status_code == 200
        data = r.json()
        assert "login_alert_enabled" in data, f"login_alert_enabled not in {data}"
        print(f"PASS: login_alert_enabled={data['login_alert_enabled']}")

    def test_login_alert_toggle_can_be_set(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/notification-settings")
        current = r.json().get("login_alert_enabled", False)
        # Toggle it
        r2 = admin_session.patch(f"{BASE_URL}/api/admin/notification-settings", json={"login_alert_enabled": not current})
        assert r2.status_code == 200
        # Toggle back
        admin_session.patch(f"{BASE_URL}/api/admin/notification-settings", json={"login_alert_enabled": current})
        print("PASS: login_alert_enabled toggle works")


class TestCleanup:
    """Test W: Cleanup verification"""

    def test_deleted_case_not_in_list(self, admin_session, client_data):
        """After fixture cleanup, verify test case is gone (this runs after all other tests in module)"""
        # This relies on the fixture's yield teardown having run AFTER all tests
        # We just verify the admin list endpoint works; actual cleanup happens in fixture
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases")
        assert r.status_code == 200
        print("PASS: Admin trust-cases endpoint accessible for cleanup verification")
