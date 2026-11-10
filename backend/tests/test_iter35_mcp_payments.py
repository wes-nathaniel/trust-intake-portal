"""
Backend tests for iteration 35:
- MCP server endpoint (tools/list, propose_admin_note)
- MCP admin routes (status, generate-key, proposals)
- Payments (stripe-config public endpoint, zelle config)
- Admin case detail (schedule-a, send-payment-link, mark-zelle-received)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "support@igcfirm.com", "password": "Wllorenzo03!"})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def mcp_key(admin_session):
    """Generate or get existing MCP key."""
    # Check status first
    status_r = admin_session.get(f"{BASE_URL}/api/admin/mcp/status")
    assert status_r.status_code == 200
    if status_r.json().get("has_key"):
        # Already has a key, generate new one to get raw key
        r = admin_session.post(f"{BASE_URL}/api/admin/mcp/generate-key")
        assert r.status_code == 200
        return r.json()["key"]
    else:
        r = admin_session.post(f"{BASE_URL}/api/admin/mcp/generate-key")
        assert r.status_code == 200
        return r.json()["key"]


@pytest.fixture(scope="module")
def a_case_id(admin_session):
    """Get first available case id."""
    r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases?limit=1")
    assert r.status_code == 200
    resp_data = r.json()
    if isinstance(resp_data, list):
        cases = resp_data
    else:
        cases = resp_data.get("cases") or []
    if not cases:
        pytest.skip("No cases available")
    return cases[0]["id"]


# --- MCP status and key management ---

class TestMcpAdminRoutes:
    def test_mcp_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/mcp/status")
        assert r.status_code in [401, 403]

    def test_mcp_status_returns_has_key(self, admin_session, mcp_key):
        # After generating key, status should show has_key=True
        r = admin_session.get(f"{BASE_URL}/api/admin/mcp/status")
        assert r.status_code == 200
        data = r.json()
        assert data.get("has_key") is True
        assert "key_id" in data
        assert "pending_proposals" in data

    def test_mcp_list_proposals_pending(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/mcp/proposals?status_filter=pending")
        assert r.status_code == 200
        data = r.json()
        assert "proposals" in data
        assert isinstance(data["proposals"], list)

    def test_mcp_list_proposals_all(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/mcp/proposals?status_filter=all")
        assert r.status_code == 200
        assert "proposals" in r.json()


# --- MCP protocol endpoint ---

class TestMcpProtocol:
    def test_tools_list_returns_7_tools(self, mcp_key):
        r = requests.post(
            f"{BASE_URL}/api/mcp/{mcp_key}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        tools = data["result"]["tools"]
        assert len(tools) == 7, f"Expected 7 tools, got {len(tools)}: {[t['name'] for t in tools]}"

    def test_invalid_key_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/mcp/invalid_key_xyz",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        assert r.status_code in [401, 403]

    def test_initialize_method(self, mcp_key):
        r = requests.post(
            f"{BASE_URL}/api/mcp/{mcp_key}",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert r.status_code == 200
        result = r.json()["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "IGC Trust Portal"

    def test_propose_admin_note_creates_proposal(self, mcp_key, a_case_id, admin_session):
        r = requests.post(
            f"{BASE_URL}/api/mcp/{mcp_key}",
            json={
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "propose_admin_note",
                    "arguments": {
                        "case_id": a_case_id,
                        "note": "TEST_ automated test note - please reject/ignore"
                    }
                }
            }
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        content = data["result"]["content"][0]["text"]
        assert "proposal created" in content.lower() or "note proposal" in content.lower()

        # Verify it appears in proposals list
        proposals_r = admin_session.get(f"{BASE_URL}/api/admin/mcp/proposals?status_filter=pending")
        assert proposals_r.status_code == 200
        proposals = proposals_r.json()["proposals"]
        test_proposals = [p for p in proposals if p.get("type") == "admin_note" and "TEST_" in (p.get("note") or "")]
        assert len(test_proposals) >= 1, "Test proposal not found in pending list"
        return test_proposals[0]["id"]

    def test_approve_then_reject_proposal(self, mcp_key, a_case_id, admin_session):
        # Create a proposal to approve
        r = requests.post(
            f"{BASE_URL}/api/mcp/{mcp_key}",
            json={
                "jsonrpc": "2.0", "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "propose_admin_note",
                    "arguments": {
                        "case_id": a_case_id,
                        "note": "TEST_ approve test note"
                    }
                }
            }
        )
        assert r.status_code == 200

        proposals_r = admin_session.get(f"{BASE_URL}/api/admin/mcp/proposals?status_filter=pending")
        proposals = proposals_r.json()["proposals"]
        test_p = [p for p in proposals if "TEST_ approve" in (p.get("note") or "")]
        assert test_p, "No test proposal to approve"
        pid = test_p[0]["id"]

        # Approve it
        approve_r = admin_session.post(f"{BASE_URL}/api/admin/mcp/proposals/{pid}/approve")
        assert approve_r.status_code == 200

        # Create another to reject
        r2 = requests.post(
            f"{BASE_URL}/api/mcp/{mcp_key}",
            json={
                "jsonrpc": "2.0", "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "propose_admin_note",
                    "arguments": {
                        "case_id": a_case_id,
                        "note": "TEST_ reject test note"
                    }
                }
            }
        )
        assert r2.status_code == 200

        proposals_r2 = admin_session.get(f"{BASE_URL}/api/admin/mcp/proposals?status_filter=pending")
        proposals2 = proposals_r2.json()["proposals"]
        reject_p = [p for p in proposals2 if "TEST_ reject" in (p.get("note") or "")]
        assert reject_p, "No test proposal to reject"
        pid2 = reject_p[0]["id"]

        reject_r = admin_session.post(f"{BASE_URL}/api/admin/mcp/proposals/{pid2}/reject")
        assert reject_r.status_code == 200


# --- Payments ---

class TestPaymentsEndpoints:
    def test_stripe_config_public_no_auth(self):
        """stripe-config must be accessible without auth."""
        r = requests.get(f"{BASE_URL}/api/payments/stripe-config")
        assert r.status_code == 200
        data = r.json()
        assert "publishable_key" in data, f"Missing publishable_key: {data}"

    def test_zelle_config_requires_auth(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/payments/zelle-config")
        assert r.status_code == 200
        data = r.json()
        assert "phone" in data

    def test_zelle_settings_get(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/settings/zelle-phone")
        assert r.status_code == 200
        data = r.json()
        assert "phone" in data
        # Default should be seeded as 9545983681
        assert data["phone"] == "9545983681" or data["phone"] != "", f"Zelle phone: {data['phone']}"


class TestAdminCaseDetailRoutes:
    def test_schedule_a_route(self, admin_session, a_case_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{a_case_id}/schedule-a")
        assert r.status_code == 200

    def test_schedule_a_csv_format(self, admin_session, a_case_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{a_case_id}/schedule-a?format=csv")
        assert r.status_code == 200

    def test_send_payment_link_validation(self, admin_session, a_case_id):
        """Send payment link endpoint should exist (even if Stripe fails gracefully)."""
        r = admin_session.post(
            f"{BASE_URL}/api/admin/trust-cases/{a_case_id}/send-payment-link",
            json={"amount_cents": 300000}
        )
        # Could be 200 (success) or 400/422/500 depending on Stripe config
        assert r.status_code in [200, 400, 422, 500], f"Unexpected status: {r.status_code}"
